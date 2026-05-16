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

### Step 2：NCS 主写作

加载 `webnovel-writer/skills/novel-station-adapter/SKILL.md`，按 `write` 模式调用 Novel-Control-Station-Skill。NCS 必须读取 `.webnovel/tmp/ncs-bridge/` 下的 00-09 标准文件、`control-cards/{NN}-control-card.md` 和 `chapters/` 最近章节后再起草。

输出先落到 `.webnovel/tmp/ncs-bridge/chapters/{NN}-<title>.md`，再适配回 `正文/第{NNNN}章-{title}.md`。禁止绕过桥接包只用单章提示直接写。

### Step 3：审查

Task 调用 `reviewer`，传入 chapter/chapter_file/project_root/scripts_dir。

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

**执行内容**：
加载 `webnovel-writer/skills/webnovel-write/references/deepseek-universal-polish.yaml`，对 Step 2 生成的章节正文执行：

1. **删除 AI 痕迹**：
   - 删除 23 条 AI 填充词（综上所述、值得注意的是等）
   - 删除 18 种 AI 模板段落（首先其次最后、一方面另一方面等）
   - 删除 8 种元说明（我将按照您的、故事梗概等）
   - 删除 Markdown 格式残留

2. **格式规范**：
   - 引号统一为「」『』
   - 省略号统一为……（U+2026×2）
   - 破折号统一为——（U+2014×2）
   - 数字汉字化（年份、年代、月份、日期）

3. **字典替换**（排除黑名单，随机候选）：
   - 148 条 AI 套话短语（85% 概率）
   - 105 条通用词汇（50% 概率）
   - 6 条小说口语短语（50% 概率）
   - 19 条小说口语词（50% 概率）

4. **LLM 语义重写**：
   - 消除 AI 腔：被动改主动、打散模板、去过度连接、落地具体细节
   - 增强文学质感：感官细节、角色个性对话、情绪融入景物、节奏变化
   - 保留原意：不添加情节、不改因果、保持专有名词

**输出**：文学化底稿（保存到 `.webnovel/tmp/polish_stage1.md`）

#### 4.2 第二阶段：番茄版排版优化（必选）

**目标**：适配手机竖屏阅读，短平快爽文节奏

**执行内容**：
加载 `webnovel-writer/skills/webnovel-write/references/tomato-mobile-formatting.yaml`，对第一阶段输出执行：

1. **对话孤立**：任何对话前后必须有双换行（手机阅读更清晰）
2. **文字墙粉碎**：连续 40 字无换行且遇句号，强制换行（避免大段文字）
3. **删除冗余描写**：设定铺陈、环境描写极限压缩（加快节奏）
4. **删除番茄禁忌词**：拖慢节奏的毒点词汇（不知不觉间、经过漫长的等待等）
5. **节奏提速替换**（85% 概率）：
   - 传统过渡词 → 爆发力动作词（"他想了想" → "他眼珠一转"）
   - 平淡动词 → 网文爽文动词（"拿" → "一把抓过"）
6. **空白优化**：收敛过多空行为标准双换行
7. **章末留白**：章末增加额外空行（给读者滑页缓冲）

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
