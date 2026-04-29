---
name: webnovel-write
description: 产出可发布章节，完整执行合同刷新→NCS桥接→NCS起草→审查→提交→备份。
allowed-tools: Read Write Edit Grep Bash Task Skill
---

# 写章流程

## 用法

```
/webnovel-writer:webnovel-write [章节号]
```

**章节号可选**：
- 如果不提供章节号，自动从 `state.json` 读取 `current_chapter + 1`
- 例如：当前写完第 1 章，直接运行 `/webnovel-writer:webnovel-write` 会自动写第 2 章

## 前置要求

**必须先运行** `/webnovel-writer:webnovel-prepare <章节号>` 生成章节合同。

如果缺少合同文件，本 skill 会在预检阶段阻断并提示用户先运行 prepare。

## 目标

产出可发布章节到 `正文/第{NNNN}章-{title}.md`。默认 2000-2500 字，用户/大纲另有要求时从之。

## 模式

| 模式 | 流程 |
|------|------|
| 默认 | Step 1→2→3→4→5→6 |
| `--fast` | Step 1→2→3(轻量)→4→5→6 |
| `--minimal` | Step 1→2→4(仅排版/终检)→5→6 |

## 硬规则

- 禁止并步、跳步、伪造审查
- blocking issue 未解决不进 Step 4/5
- 失败只补跑失败步骤，不回退
- 参考资料按步骤按需加载
- 写正文前必须生成 `.webnovel/tmp/ncs-bridge/`，不得绕过 NCS bridge 直接起草
- NCS 写作必须读取 00-09 标准文件、`control-cards/`、最近章节与正文连续性上下文

## 优先级

用户要求 > 状态机硬门槛 > 项目约束（总纲/设定/记忆）> skill 流程 > reference 建议

## CSV 检索（Step 2 按需）

```bash
python -X utf8 "${SCRIPTS_DIR}/reference_search.py" --skill write --table {表名} --query "{关键词}" --genre {题材}
```

触发条件：新角色→命名规则，战斗→场景写法，多角色对话→写作技法，情感描写→写作技法，高频桥段→场景写法。

## 执行流程

### 准备：预检

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?}/scripts"
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT:?}/skills/webnovel-write"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

### 准备：确定章节号

如果用户未提供章节号，从 state.json 自动读取：

```bash
if [ -z "${CHAPTER_NUM}" ]; then
  CHAPTER_NUM=$(python -X utf8 -c "import json,sys; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('progress',{}).get('current_chapter',0)+1)")
  echo "自动检测到下一章节号: ${CHAPTER_NUM}"
fi
```

### 准备：刷新合同树

genre 从 state.json 读取（唯一真源），query 填章纲目标（用于 CSV 检索）。

```bash
GENRE="$(python -X utf8 -c "import json,sys; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('project',{}).get('genre',''))")"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  story-system "{章纲目标}" --genre "${GENRE}" --chapter {chapter_num} --persist --emit-runtime-contracts --format both
```

必备文件：`MASTER_SETTING.json`（调性/禁忌）、`volume_{NNN}.json`（卷级节奏）、`chapter_{NNN}.review.json`（必须节点/禁区）。缺失则阻断。

`chapter_{NNN}.json` 的 `chapter_focus` 仅为 CSV 参考，本章目标以章纲为准。核心价值是 `reasoning` 裁决元数据。

### Step 1：生成 NCS 上下文包

先生成 Novel-Control-Station 标准桥接包。这个步骤是写作主链的硬门槛，不是可选润色资料。

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  ncs-bridge --chapter "${CHAPTER_NUM}" --recent-chapters 3
```

必备产物：
- `.webnovel/tmp/ncs-bridge/00-project-overview.md`
- `.webnovel/tmp/ncs-bridge/02-worldbuilding.md`
- `.webnovel/tmp/ncs-bridge/03-cast-bible.md`
- `.webnovel/tmp/ncs-bridge/05-main-plotlines.md`
- `.webnovel/tmp/ncs-bridge/06-foreshadow-ledger.md`
- `.webnovel/tmp/ncs-bridge/07-chapter-roadmap.md`
- `.webnovel/tmp/ncs-bridge/08-dynamic-state.md`
- `.webnovel/tmp/ncs-bridge/09-style-guide.md`
- `.webnovel/tmp/ncs-bridge/control-cards/{NN}-control-card.md`
- `.webnovel/tmp/ncs-bridge/chapters/` 最近章节上下文

这些文件会汇总人物卡、角色库、世界观、力量体系、总纲、卷详细大纲、卷时间线、卷节拍表、章节合同、审查合同、最近摘要、近期事件、主角状态、伏笔和运行态情节线。

### Step 2：NCS 主写作

加载 `../novel-station-adapter/SKILL.md`，按 `write` 模式调用 Novel-Control-Station-Skill。NCS 是本步骤的正文生成器，不是后置修辞插件。

NCS 必须读取：
- `00-project-overview.md` 到 `09-style-guide.md`
- `control-cards/{NN}-control-card.md`
- `chapters/` 中最近章节
- 章级合同中的 CBN/CPNs/CEN、must_cover_nodes、forbidden_in_chapter

NCS 输出到 `.webnovel/tmp/ncs-bridge/chapters/{NN}-<title>.md` 后，再适配回 `正文/第{NNNN}章-{title}.md`。

禁止只根据临时任务书或单章提示直接起草。需要局部检索 CSV 时，只能作为 NCS 控制卡/写作提示的补充，不能覆盖桥接包中的时间线、人物状态和合同约束。

### Step 3：审查

Task 调用 `reviewer`，传入 chapter/chapter_file/project_root/scripts_dir。

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline \
  --chapter {chapter_num} \
  --review-results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --metrics-out "${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json" \
  --report-file "审查报告/第{chapter_num}章审查报告.md" \
  --save-metrics
```

blocking=true → 修复后重审，不进 Step 4。`--fast` 只检查 setting/timeline/continuity。`--minimal` 跳过。

### Step 4：NCS 复查与轻润色

优先加载 `../novel-station-adapter/SKILL.md`、`polish-guide.md`、`typesetting.md`、`style-adapter.md`。

顺序：修复非 blocking issue → 调用 Novel-Control-Station-Skill 的 `polish` / authenticity pass → 风格适配 → 排版 → NCS 终检。

NCS 润色默认走 safe 路线：先保留稳定底稿，只局部削高风险句型；必要时只打散最扎眼的一组段落。默认不靠额外补“人味句”来制造真人感。

只改表达不改事实。`anti_ai_force_check=pass|fail` 继续作为 Step 5 的放行标记；`fail` 时不进 Step 5。`--minimal` 仅排版。`--fast` 可简化重写深度，但不能跳过终检 gate。

### Step 5：提交

#### 5.1 Data Agent 提取事实

Task 调用 `data-agent`，产出 review_results / fulfillment_result / disambiguation_result / extraction_result 四份 JSON。

Data Agent 只提取事实+生成 artifacts，不直接写 state/index/summaries/memory。

#### 5.2 CHAPTER_COMMIT

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter {chapter_num} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

自动判定：blocking_count>0 或 missed_nodes 非空 或 pending 非空 → rejected，否则 accepted。

#### 5.3 验证投影

projection_status 五项（state/index/summary/memory/vector）全部 done 或 skipped。

chapter_status 由 projection writer 自动推进：accepted→committed，rejected→rejected。

#### 5.4 失败隔离

commit 未生成→重跑 5.2。projection 失败→只补跑失败项。不回退 Step 1-4。

### Step 6：Git 备份

```bash
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第{chapter_num}章: {title}"
```

## 充分性闸门

1. 正文文件存在且非空
2. 审查已落库（`--minimal` 除外）
3. blocking=true 必须停在 Step 3
4. anti_ai_force_check=pass（`--minimal` 除外）
5. accepted CHAPTER_COMMIT，projection 五项 done/skipped
6. chapter_status=committed（projection 自动推进）

## 失败恢复

审查缺失→重跑 Step 3。摘要/状态/记忆缺失→重跑 Step 5。润色失真→回 Step 4 修复后重跑 Step 5。
