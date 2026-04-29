---
name: novel-station-adapter
description: 双向适配器：webnovel-writer ↔ Novel-Control-Station，利用 NCS 的去AI能力提升章节质量
allowed-tools: Read Write Edit Grep Bash Skill
---

# Novel Station 双向适配器

> 本 skill 是本仓库连接 `Novel-Control-Station-Skill` 的主桥接层。
> `webnovel-write` / `webnovel-chapter` 的正文起草阶段默认通过这里进入 NCS；输出仍回写到 webnovel-writer 的标准目录与状态链路，以保持面板和后续提交流程兼容。

## 用法

### 模式1: 章节生成（推荐）
```bash
/webnovel-writer:novel-station-adapter write [章节号]
```
使用 Novel-Control-Station 作为主写作引擎生成章节，适配回 webnovel-writer。

### 模式2: 项目同步
```bash
/webnovel-writer:novel-station-adapter sync
```
将 webnovel-writer 项目数据同步为 Novel-Control-Station 标准文件，保持双向一致。

### 模式3: 润色增强
```bash
/webnovel-writer:novel-station-adapter polish [章节号]
```
对已生成的章节使用 NCS 的去AI系统进行深度润色。

## 目标

- 利用 Novel-Control-Station 的强大去AI能力、文学标准和正文生成链路
- 保持 webnovel-writer 的工作流和项目结构
- 实现两个系统的优势互补

## 前置要求

1. Novel-Control-Station-Skill 已安装在 `/Users/liangfushou/project/小说/new/Novel-Control-Station-Skill`
2. 当前项目已完成 `/webnovel-writer:webnovel-init`
3. 对于 write 模式，需要先运行 `/webnovel-writer:webnovel-prepare [章节号]`

## 硬规则

- 不修改 Novel-Control-Station 的 SKILL.md 或 references
- 所有转换在 `.webnovel/tmp/ncs-bridge/` 临时目录完成
- 保持 webnovel-writer 的 state.json 为唯一真源
- NCS 生成的章节必须经过 webnovel-writer 的 data-agent 提取和 commit 流程
- 转换必须保留原项目的题材、调性、禁忌约束
- `write` 模式是当前写章主线；不得绕过 `.webnovel/tmp/ncs-bridge/` 只用单章提示起草
- NCS 起草前必须读取 00-09 标准文件、`control-cards/` 和 `chapters/` 最近章节

## 优先级

用户要求 > webnovel-writer state.json > NCS 标准文件 > 生成建议

---

## 模式1: 章节生成 (write)

### Step 1: 环境准备与上下文读取

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?}/scripts"
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
export NCS_ROOT="/Users/liangfushou/project/小说/new/Novel-Control-Station-Skill"
export BRIDGE_DIR="${PROJECT_ROOT}/.webnovel/tmp/ncs-bridge"

# 确定章节号
if [ -z "${CHAPTER_NUM}" ]; then
  CHAPTER_NUM=$(python -X utf8 -c "import json; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('progress',{}).get('current_chapter',0)+1)")
fi

# 生成 NCS 标准桥接文件
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  ncs-bridge --chapter "${CHAPTER_NUM}" --recent-chapters 3
```

`ncs-bridge` 会读取并转换这些必要文件：
- `.webnovel/state.json` - 项目状态和题材
- `大纲/总纲.md` - 故事主线
- `大纲/第{volume_id}卷-详细大纲.md` - 卷纲和章纲
- `大纲/第{volume_id}卷-时间线.md` - 卷级时间锚点
- `大纲/第{volume_id}卷-节拍表.md` - 卷级节奏和高低潮
- `设定集/世界观.md` - 世界设定
- `设定集/力量体系.md` - 力量规则
- `设定集/主角卡.md` - 主角信息
- `设定集/反派设计.md` - 反派层级
- `设定集/角色库/` - 主要角色、次要角色、反派角色
- `.webnovel/contracts/chapter_{NNN}.json` - 章节合同（结构化节点）
- `.story-system/MASTER_SETTING.json` - 调性和禁忌
- `.webnovel/summaries/` - 最近5章摘要（了解剧情进度）

### Step 2: 转换为 NCS 标准文件

`ncs-bridge` 会在 `${BRIDGE_DIR}` 创建 NCS 标准文件结构。以下内容为生成规则和校验口径：

#### 2.1 生成 00-project-overview.md

```markdown
# 项目概览

**项目名称**: {从 state.json project.title}
**题材**: {从 state.json project.genre}
**目标字数**: {从 state.json project.target_words}
**发布模式**: 网文连载

## 核心设定

{从 总纲.md 提取：一句话故事、核心冲突、主线暗线}

## 创意约束

{从 .webnovel/idea_bank.json 提取：反套路、硬约束}
```

#### 2.2 生成 03-cast-bible.md

从 `设定集/主角卡.md` 和 `设定集/反派设计.md` 转换：

```markdown
# 角色圣经

## {主角名}

- **角色定位**: 主角
- **核心人格**: {从主角卡提取}
- **可见目标**: {从 protagonist_desire 转换}
- **内在缺失**: {从 protagonist_flaw 转换}
- **关键关系**: {从 relationship 字段提取}
- **矛盾点**: {从 flaw 和 desire 的冲突推导}
- **弧线方向**: {从总纲的主角成长线提取}
- **说话特征**: {从已写章节中提取，如有}

## {反派名}

{按 NCS 格式重组反派信息}
```

#### 2.3 生成 02-worldbuilding.md

从 `设定集/世界观.md` 和 `设定集/力量体系.md` 整合。

#### 2.4 生成 05-main-plotlines.md

从 `大纲/总纲.md` 和当前卷纲提取：

```markdown
# 主要情节线

## 主线：{核心主线}

**当前状态**: 第{volume}卷第{chapter}章
**已完成节点**: {从 summaries 提取关键事件}
**下一目标**: {从章纲提取本章目标}

## 支线：{如有}

{从卷纲的 Strand 分布提取}
```

#### 2.5 生成 07-chapter-roadmap.md

从 `大纲/第{volume_id}卷-详细大纲.md` 提取当前章节及前后章节：

```markdown
# 章节路线图

## 第{N-1}章：{标题}
{简要目标和结果}

## 第{N}章：{标题}（当前章）
**目标**: {从章纲提取}
**阻力**: {从章纲提取}
**代价**: {从章纲提取}
**爽点**: {从章纲提取}
**章末钩子**: {从章纲提取}

## 第{N+1}章：{标题}
{简要目标}
```

#### 2.6 生成 08-dynamic-state.md

```markdown
# 动态状态

## 当前进度
- 卷: 第{volume}卷
- 章: 第{chapter}章
- 字数: {从 state.json 读取}

## 角色当前状态

{从 .webnovel/knowledge/ 查询主要角色的最新状态}

## 活跃情节线

{从 memory-contract 的 open-loops 提取}

## 待回收伏笔

{从 .webnovel/contracts 提取未完成的伏笔}
```

#### 2.7 生成 09-style-guide.md

从 `.story-system/MASTER_SETTING.json` 转换：

```markdown
# 风格指南

## 段落模式
web-serial-natural

## 风格平衡目标
{从 MASTER_SETTING tone 转换}

## 调性约束
{从 MASTER_SETTING forbidden_patterns 转换}

## 术语上限
{从 jargon_ceiling 转换}

## 禁忌列表
{从 forbidden_patterns 详细展开}

## 必须保留术语
{从 power_system 提取专有名词}
```

#### 2.8 生成 06-foreshadow-ledger.md

从 `.webnovel/contracts` 和 `memory-contract` 提取伏笔信息。

#### 2.9 创建 chapters/ 和 control-cards/ 目录

```bash
mkdir -p "${BRIDGE_DIR}/chapters"
mkdir -p "${BRIDGE_DIR}/control-cards"
mkdir -p "${BRIDGE_DIR}/logs"
```

如果有已完成章节，复制最近3章到 `chapters/` 供 NCS 参考连贯性。

### Step 3: 生成章节控制卡（NCS 格式）

基于 `.webnovel/contracts/chapter_{NNN}.json` 生成 NCS 控制卡：

```markdown
# 第{N}章控制卡

## 章节任务
{从章纲的目标、阻力、代价整合}

## 必须节点（来自 webnovel-writer）
- CBN: {章节起点}
- CPN1: {推进节点1}
- CPN2: {推进节点2}
- CEN: {章节终点}

## 必须覆盖
{从 chapter contract 的 must_cover_nodes 提取}

## 本章禁区
{从 chapter contract 的 forbidden_in_chapter 提取}

## 风格控制
- 段落模式: web-serial-natural
- 风格强度: {从 MASTER_SETTING 推导}
- 活跃风格驱动: {从题材和章纲目标推导}

## 预期字数
2000-2500字（webnovel-writer 标准）

## 连贯性检查点
- 上章结尾: {从 summary 提取}
- 角色状态: {从 knowledge 提取}
- 时间锚点: {从章纲提取}
```

### Step 4: 调用 Novel-Control-Station

切换到桥接目录并调用 NCS：

```bash
cd "${BRIDGE_DIR}"
```

使用 Skill 工具调用 `/novel-control-station`，传递上下文：

**明确告知 NCS**：
- 当前在第{N}章
- 标准文件已准备在当前目录
- 章节控制卡在 `control-cards/` 
- 目标字数 2000-2500
- 必须覆盖结构化节点（CBN/CPNs/CEN）
- 必须遵守本章禁区
- 段落模式为 web-serial-natural

**NCS 执行流程**（自动）：
1. 读取标准文件（00-09）
2. 读取章节控制卡
3. 读取 `chapters/` 最近章节，确认上章结尾、人物状态、时间锚点
4. 起草章节
5. 运行基准检查
6. 执行去AI润色（authenticity pass）
7. 后润色复查
8. 输出到 `chapters/NN-*.md`

### Step 5: 提取并适配章节

从 NCS 输出提取：

```bash
NCS_CHAPTER=$(ls "${BRIDGE_DIR}/chapters/" | grep "^$(printf '%02d' ${CHAPTER_NUM})-")
CHAPTER_TITLE=$(echo "${NCS_CHAPTER}" | sed 's/^[0-9]*-//;s/\.md$//')
```

将章节内容复制到 webnovel-writer 正文目录：

```bash
cp "${BRIDGE_DIR}/chapters/${NCS_CHAPTER}" \
   "${PROJECT_ROOT}/正文/第$(printf '%04d' ${CHAPTER_NUM})章-${CHAPTER_TITLE}.md"
```

保留 NCS 控制卡用于分析：

```bash
mkdir -p "${PROJECT_ROOT}/.webnovel/ncs-artifacts/control-cards"
cp "${BRIDGE_DIR}/control-cards/"* \
   "${PROJECT_ROOT}/.webnovel/ncs-artifacts/control-cards/"
```

### Step 6: webnovel-writer 提交流程

#### 6.1 调用 data-agent 提取事实

使用 Task 工具调用 data-agent，传入：
- chapter: {CHAPTER_NUM}
- chapter_file: `正文/第{NNNN}章-{title}.md`
- project_root: ${PROJECT_ROOT}
- scripts_dir: ${SCRIPTS_DIR}

产出四份 JSON：
- review_results.json
- fulfillment_result.json
- disambiguation_result.json
- extraction_result.json

#### 6.2 执行 CHAPTER_COMMIT

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter ${CHAPTER_NUM} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

#### 6.3 验证投影

确认 projection_status 五项全部 done/skipped，chapter_status 为 committed。

### Step 7: Git 备份

```bash
cd "${PROJECT_ROOT}"
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第${CHAPTER_NUM}章: ${CHAPTER_TITLE} (via Novel-Control-Station)"
```

---

## 模式2: 项目同步 (sync)

将 webnovel-writer 项目完整转换为 NCS 标准文件，用于：
- 让 NCS 接管后续章节生成
- 利用 NCS 的 marathon 模式批量生成
- 进行全局一致性检查

### 执行流程

1. 读取 webnovel-writer 全部项目文件
2. 按 Step 2 的规则生成完整 NCS 标准文件
3. 将已完成章节全部复制到 NCS 的 chapters/
4. 生成对应的 control-cards/
5. 更新 logs/writing-log.md
6. 输出同步报告

同步后，可以直接在 NCS 项目中继续工作，或使用 marathon 模式。

---

## 模式3: 润色增强 (polish)

对已生成的章节进行 NCS 深度润色。

### 执行流程

1. 读取指定章节：`正文/第{NNNN}章-{title}.md`
2. 准备 NCS 上下文（同 Step 1-2）
3. 将章节复制到 `${BRIDGE_DIR}/chapters/`
4. 调用 NCS 的 authenticity pass：
   - 加载 `authenticity-and-de-ai-pass.md`
   - 加载 `09-style-guide.md`
   - 执行三阶段润色：
     1. 去除AI痕迹
     2. 削减术语和分析语言
     3. 恢复具体细节和节奏变化
5. 运行后润色复查
6. 将润色后的章节写回 `正文/`
7. 更新 Git

---

## 格式转换映射表

### webnovel-writer → NCS

| webnovel-writer | NCS 标准文件 | 转换规则 |
|----------------|-------------|---------|
| state.json | 00-project-overview.md | 提取 title/genre/target_words |
| 大纲/总纲.md | 00 + 05-main-plotlines.md | 核心冲突→主线，支线→plotlines |
| 设定集/主角卡.md | 03-cast-bible.md | 重组为 NCS 8字段格式 |
| 设定集/世界观.md | 02-worldbuilding.md | 直接映射 |
| 设定集/力量体系.md | 02-worldbuilding.md | 合并到世界观 |
| 设定集/反派设计.md | 03-cast-bible.md | 按层级展开 |
| 大纲/卷详细大纲.md | 07-chapter-roadmap.md | 提取章节序列 |
| .webnovel/summaries/ | 08-dynamic-state.md | 最新状态 |
| .story-system/MASTER_SETTING.json | 09-style-guide.md | 调性→风格，禁忌→约束 |
| .webnovel/contracts/chapter_*.json | control-cards/*.md | CBN/CPNs/CEN→必须节点 |
| .webnovel/knowledge/ | 08-dynamic-state.md | 角色/关系状态 |
| .webnovel/memory-contract | 06-foreshadow-ledger.md | open-loops→伏笔 |

### NCS → webnovel-writer

| NCS 输出 | webnovel-writer | 转换规则 |
|---------|----------------|---------|
| chapters/NN-*.md | 正文/第NNNN章-*.md | 重命名为4位数 |
| control-cards/ | .webnovel/ncs-artifacts/ | 保留用于分析 |
| 08-dynamic-state.md 更新 | 通过 data-agent 提取 | 不直接覆盖 state.json |

---

## 优势对比

### Novel-Control-Station 优势
- 强大的去AI系统（三阶段润色）
- 文学标准和基准检查
- 完整的风格模块系统
- 段落模式精细控制
- 遗忘元素和线索热度管理

### webnovel-writer 优势
- 结构化节点（CBN/CPNs/CEN）
- 自动化的 data-agent 提取
- 知识图谱和关系追踪
- CSV 创作参考检索
- 完整的项目状态机

### 适配器价值
- 结合两者优势
- NCS 负责文本质量和去AI
- webnovel-writer 负责结构控制和状态管理
- 用户可根据需求选择模式

---

## 注意事项

1. **字数控制**: NCS 可能生成超过 2500 字的章节，如需严格控制，在调用时明确传递字数上限
2. **结构化节点**: 必须在控制卡中明确 CBN/CPNs/CEN，确保 NCS 覆盖这些节点
3. **禁区遵守**: 将 webnovel-writer 的 forbidden_in_chapter 完整传递给 NCS
4. **术语保留**: 从 power_system 提取的专有名词必须写入 09-style-guide.md 的"必须保留术语"
5. **时间一致性**: 确保时间锚点在转换中不丢失
6. **伏笔连续性**: open-loops 必须完整转换为 foreshadow-ledger
7. **Git 冲突**: 两个系统同时工作时注意文件冲突

---

## 失败恢复

### 转换失败
- 检查必要文件是否存在
- 验证 state.json 格式
- 确认 NCS_ROOT 路径正确

### NCS 调用失败
- 检查标准文件完整性
- 验证控制卡格式
- 确认章节号正确

### commit 失败
- 重跑 data-agent
- 检查 projection 状态
- 只补跑失败项，不回退 NCS 生成

---

## 使用建议

**首次使用**：
1. 先运行 `sync` 模式，确保转换正确
2. 检查生成的 NCS 标准文件
3. 再使用 `write` 模式生成章节

**日常使用**：
- 推荐入口：`/webnovel-writer:webnovel-chapter [章节号]`
- 只做 NCS 章节生成：`/webnovel-writer:novel-station-adapter write [章节号]`
- 只对既有章节补救：`polish` 模式

**批量生成**：
1. 运行 `sync` 同步项目
2. 在 NCS 项目中使用 marathon 模式
3. 生成完成后批量导回 webnovel-writer
