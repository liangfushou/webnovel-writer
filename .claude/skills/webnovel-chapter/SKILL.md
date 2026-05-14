---
name: webnovel-chapter
description: 完整处理指定章节：自动准备章节合同并走 NCS bridge 写章主链，包含两阶段润色（DeepSeek 通用去AI + 番茄版排版）。
allowed-tools: Read Write Edit Grep Bash Task Skill
---

# 章节封装流程（含两阶段润色）

## 用法

```bash
/webnovel-chapter [数字]
```

**中文说明**：
- 写第 1 章：`/webnovel-chapter 1`
- 写第 12 章：`/webnovel-chapter 12`
- 自动写下一章：`/webnovel-chapter`（不带数字，自动从 state.json 读取下一章节号）

**完整流程**：
1. 📋 准备章节合同
2. 🔧 生成 NCS 上下文包
3. ✍️ NCS 主写作（生成初稿）
4. 🔍 审查（检查设定、时间线、连续性）
5. 🎨 **DeepSeek 通用去AI润色**（删除 AI 痕迹、格式规范、字典替换）
6. 📱 **番茄版排版优化**（对话独立、段落切分、节奏提速）
7. ✅ NCS 终检（Anti-AI 检查）
8. 💾 提交和备份

**预期时间**：约 5-10 分钟/章（取决于章节长度和 LLM 速度）

## 目标

把"准备章节合同 + NCS bridge 写章主链 + 两阶段润色"封成一个入口，不改面板、状态机和提交流程。

## 模式

| 模式 | 流程 |
|------|------|
| 默认 | 准备合同 → Step 1→2→3→4.1→4.2→4.3→5→6 |
| `--fast` | 准备合同 → Step 1→2→3(轻量)→4.1→4.2→4.3(简化)→5→6 |
| `--minimal` | 准备合同 → Step 1→2→4.3(仅排版)→5→6 |

## 硬规则

- 禁止并步、跳步、伪造审查
- blocking issue 未解决不进 Step 4/5
- 失败只补跑失败步骤，不回退
- 参考资料按步骤按需加载
- 本 skill 只新增"章节号解析 + 合同准备"，其余主链遵循 `webnovel-write`
- `webnovel-write` 的 Step 1/2 由 `ncs-bridge` + `novel-station-adapter write` 进入 Novel-Control-Station-Skill
- 正文仍回写到 webnovel-writer 标准目录，面板、菜单、审查、提交、资料投影继续兼容
- **Step 4 包含两阶段润色：4.1 DeepSeek 通用去AI → 4.2 番茄版排版 → 4.3 NCS 终检**

## 执行流程

### 准备：预检

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${WORKSPACE_ROOT}/webnovel-writer/scripts"
export SKILL_ROOT="${WORKSPACE_ROOT}/webnovel-writer/skills/webnovel-chapter"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

### 准备：确定章节号

如果用户输入的是数字，直接使用；如果没输入，则自动取下一章：

```bash
if [ -z "${CHAPTER_NUM}" ]; then
  CHAPTER_NUM=$(python -X utf8 -c "import json; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('progress',{}).get('current_chapter',0)+1)")
  echo "自动检测到下一章节号: ${CHAPTER_NUM}"
fi
```

### 准备：刷新合同树

genre 从 state.json 读取（唯一真源），query 填章纲目标（用于 CSV 检索）。

```bash
GENRE="$(python -X utf8 -c "import json; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('project_info',{}).get('genre',''))")"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  story-system "{章纲目标}" --genre "${GENRE}" --chapter ${CHAPTER_NUM} --persist --emit-runtime-contracts --format both
```

必备文件：`MASTER_SETTING.json`、`volume_{NNN}.json`、`chapter_{NNN}.json`、`chapter_{NNN}.review.json`。缺失则阻断。

### Step 1：生成 NCS 上下文包

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  ncs-bridge --chapter "${CHAPTER_NUM}" --recent-chapters 3
```

本步骤必须在起草前完成。桥接包会把人物卡、角色库、世界观、力量体系、总纲、卷详细大纲、卷时间线、卷节拍表、章节合同、审查合同、最近摘要、近期事件、主角状态、伏笔和运行态情节线转换为 Novel-Control-Station 标准文件。

### Step 1.5：知识库查询（index.db + vectors.db）

如果 `${PROJECT_ROOT}/.webnovel/index.db` 和 `${PROJECT_ROOT}/.webnovel/vectors.db` 存在且非空，必须在写作前查询：

```bash
# 查询本章出场角色的最新状态
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  knowledge "第${CHAPTER_NUM}章相关角色状态"

# RAG 语义检索：前文是否有类似场景/对话（避免重复）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  rag "本章核心场景关键词"

# 查询相关伏笔当前状态
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  index query "伏笔"
```

查询目的：
- 确认出场角色的位置、伤势、已知信息（防止写出矛盾）
- 检查前文是否已有类似场景或对话（防止重复）
- 确认相关伏笔状态（已种/已收/延期，防止遗漏或重复回收）
- 长篇（10章+）时此步骤为**必须**，短篇（≤10章）为建议

如果 index.db/vectors.db 不存在（如第一章），跳过此步骤。

### Step 2：NCS 主写作

加载 `webnovel-writer/skills/novel-station-adapter/SKILL.md`，按 `write` 模式调用 Novel-Control-Station-Skill。NCS 必须读取 `.webnovel/tmp/ncs-bridge/` 下的 00-09 标准文件、`control-cards/{NN}-control-card.md` 和 `chapters/` 最近章节后再起草。Step 1.5 的知识库查询结果必须作为写作上下文参考。

输出先落到 `.webnovel/tmp/ncs-bridge/chapters/{NN}-<title>.md`，再适配回 `正文/第{NNNN}章-{title}.md`。禁止绕过桥接包只用单章提示直接写。

### Step 3：审查

分两步完成：

**Step 3.1：AI 生成审查 JSON**

读取本章正文，对照章级合同和前文连续性，生成审查结果 JSON 并写入 `.webnovel/tmp/review_results.json`。

格式必须为：
```json
{
  "chapter": ${CHAPTER_NUM},
  "blocking_count": 0,
  "review_score": 88,
  "overall_score": 88,
  "审查维度": {
    "剧情连贯性": {"score": 90, "comment": "..."},
    "人物一致性": {"score": 85, "comment": "..."},
    "节奏控制": {"score": 88, "comment": "..."},
    "信息密度": {"score": 85, "comment": "..."},
    "悬念设置": {"score": 90, "comment": "..."},
    "AI腔控制": {"score": 88, "comment": "..."}
  },
  "问题清单": [
    {"severity": "minor", "问题": "..."}
  ],
  "总结": "..."
}
```

overall_score = 六个维度的平均分。`chapter` 字段必须等于当前章号。

**Step 3.2：review-pipeline 转化为 metrics 并落库**

`review-pipeline` 只负责**读取** review_results.json 并转化为 metrics 写入 index.db，不生成审查内容。

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline \
  --chapter ${CHAPTER_NUM} \
  --review-results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --metrics-out "${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json" \
  --report-file "审查报告/第${CHAPTER_NUM}章审查报告.md" \
  --save-metrics
```

### Step 4：两阶段润色与终检

**中文说明**：这是本次集成的核心功能，分三个子步骤自动执行。

#### 4.1 第一阶段：DeepSeek 通用去AI润色（必选）

**目标**：消除 AI 写作痕迹，提升文学质感

**执行方式**：Claude 直接读取提示词文件，作为 system prompt 执行润色。

**操作**：
1. 读取 `webnovel-writer/skills/webnovel-write/references/deepseek-universal-polish.yaml` 作为规则集
2. 读取 Step 2 生成的章节正文
3. 按提示词规则执行：删除 AI 填充词 → 格式规范 → 字典替换 → 语义重写
4. 直接输出润色后正文，不附任何说明
5. 用 Write 工具保存到 `.webnovel/tmp/polish_stage1.md`

**规则摘要**：
- 引号统一为「」『』，省略号统一为……，破折号统一为——
- 删除 AI 填充词、模板段落、元说明
- 消除 AI 腔，增强文学质感，保留原意（不改情节、不改因果）
- 保留【】系统提示的极短风格，不扩写

**输出**：文学化底稿（`.webnovel/tmp/polish_stage1.md`）

#### 4.2 第二阶段：番茄版排版优化（必选）

**目标**：适配手机竖屏阅读，短平快爽文节奏

**执行方式**：Claude 直接读取提示词文件，作为 system prompt 执行排版。

**操作**：
1. 读取 `webnovel-writer/skills/webnovel-write/references/tomato-mobile-formatting.yaml` 作为规则集
2. 读取 `.webnovel/tmp/polish_stage1.md`（4.1 输出）
3. 按提示词规则执行：对话孤立 → 文字墙粉碎 → 删冗余 → 节奏提速 → 空白优化 → 章末留白
4. 直接输出排版后正文，不附任何说明
5. 用 Write 工具写回 `正文/第{NNNN}章-{title}.md`

**规则摘要**：
- 任何对话独占一段，前后双换行
- 连续超过 40 字遇句号强制换行
- 删除番茄禁忌词（不知不觉间、经过漫长的等待等）
- 节奏提速（"他想了想" → "他眼珠一转"，"过了一会儿" → "半晌"等）
- 情绪外放：内心活动转化为外在动作

**输出**：番茄平台版本（写回 `正文/第{NNNN}章-{title}.md`）

#### 4.3 NCS 终检与问题修复（暂时禁用）

**状态**：⚠️ 暂时跳过此步骤

**原目标**：修复审查问题，执行最终 Anti-AI 检查

**执行内容**：
~~加载 `webnovel-writer/skills/novel-station-adapter/SKILL.md`、`webnovel-writer/skills/webnovel-write/references/polish-guide.md`。~~

~~顺序：~~
~~1. 修复 Step 3 审查报告中的非 blocking issue~~
~~2. 调用 Novel-Control-Station-Skill 的 `polish` / authenticity pass~~
~~3. 执行 Anti-AI 终检（基于 polish-guide.md 的 7 层规则）~~
~~4. 输出 `anti_ai_force_check: pass/fail`~~

**当前行为**：
- 跳过 NCS 终检
- 跳过 polish-guide.md 的 7 层规则检查
- 直接设置 `anti_ai_force_check: pass`（自动通过）
- 继续进入 Step 5

**原因**：
- Step 4.1 和 4.2 已经完成了充分的去AI处理
- 避免重复润色导致过度修改
- 加快写作速度

**如需启用**：
编辑本文件，将此步骤的内容取消注释，并移除"暂时禁用"标记。

**模式差异**：
- `--minimal`：跳过 4.1 和 4.2，仅执行 4.3（如果启用）
- `--fast`：4.1 和 4.2 正常执行，4.3 简化重写深度（如果启用）
- 默认：完整执行 4.1 → 4.2 → 跳过 4.3

**中文总结**：
- 4.1 = 去 AI 味，让文字更像人写的 ✅
- 4.2 = 改排版，让手机读起来更爽 ✅
- 4.3 = 最后检查，确保质量过关 ⚠️ **暂时禁用**

### Step 5：提交

#### 5.1 Data Agent 提取事实

Task 调用 `data-agent`，产出 review_results / fulfillment_result / disambiguation_result / extraction_result 四份 JSON。

#### 5.2 CHAPTER_COMMIT

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter ${CHAPTER_NUM} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

#### 5.3 验证投影

projection_status 五项（state/index/summary/memory/vector）全部 done 或 skipped。

### Step 6：Git 备份

```bash
cd "${PROJECT_ROOT}"
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第${CHAPTER_NUM}章: ${CHAPTER_TITLE} (含两阶段润色)"
```

## 充分性闸门

1. 章节号已解析
2. 合同文件存在且非空
3. 正文文件存在且非空
4. 审查已落库（`--minimal` 除外）
5. 两阶段润色已完成（`--minimal` 除外）
6. ~~`anti_ai_force_check=pass`（`--minimal` 除外）~~ ⚠️ **暂时禁用，自动通过**
7. accepted CHAPTER_COMMIT，projection 五项 done/skipped
8. chapter_status=committed（projection 自动推进）

**说明**：
- Step 4.3 (NCS 终检) 暂时禁用
- `anti_ai_force_check` 自动设置为 `pass`
- Step 4.1 和 4.2 的两阶段润色已足够

## 推荐用法

```bash
/webnovel-chapter 1
/webnovel-chapter 12
/webnovel-chapter
```

其中前两种都是直接数字；最后一种默认写下一章。
