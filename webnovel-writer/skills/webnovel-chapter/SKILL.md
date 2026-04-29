---
name: webnovel-chapter
description: 完整处理指定章节：自动准备章节合同并走 NCS bridge 写章主链。
allowed-tools: Read Write Edit Grep Bash Task Skill
---

# 章节封装流程

## 用法

```bash
/webnovel-writer:webnovel-chapter [数字]
```

- 可以直接写数字：`/webnovel-writer:webnovel-chapter 12`
- 不写数字时，自动取 `.webnovel/state.json` 中 `current_chapter + 1`

## 目标

把“准备章节合同 + NCS bridge 写章主链”封成一个入口，不改面板、状态机和提交流程。

## 模式

| 模式 | 流程 |
|------|------|
| 默认 | 准备合同 → Step 1→2→3→4→5→6 |
| `--fast` | 准备合同 → Step 1→2→3(轻量)→4→5→6 |
| `--minimal` | 准备合同 → Step 1→2→4(仅排版)→5→6 |

## 硬规则

- 禁止并步、跳步、伪造审查
- blocking issue 未解决不进 Step 4/5
- 失败只补跑失败步骤，不回退
- 参考资料按步骤按需加载
- 本 skill 只新增“章节号解析 + 合同准备”，其余主链遵循 `webnovel-write`
- `webnovel-write` 的 Step 1/2 由 `ncs-bridge` + `novel-station-adapter write` 进入 Novel-Control-Station-Skill
- 正文仍回写到 webnovel-writer 标准目录，面板、菜单、审查、提交、资料投影继续兼容

## 执行流程

### 准备：预检

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?}/scripts"
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT:?}/skills/webnovel-chapter"

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
  story-system "{章纲目标}" --genre "${GENRE}" --chapter {chapter_num} --persist --emit-runtime-contracts --format both
```

必备文件：`MASTER_SETTING.json`、`volume_{NNN}.json`、`chapter_{NNN}.json`、`chapter_{NNN}.review.json`。缺失则阻断。

### Step 1：生成 NCS 上下文包

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  ncs-bridge --chapter "${CHAPTER_NUM}" --recent-chapters 3
```

本步骤必须在起草前完成。桥接包会把人物卡、角色库、世界观、力量体系、总纲、卷详细大纲、卷时间线、卷节拍表、章节合同、审查合同、最近摘要、近期事件、主角状态、伏笔和运行态情节线转换为 Novel-Control-Station 标准文件。

### Step 2：NCS 主写作

加载 `../novel-station-adapter/SKILL.md`，按 `write` 模式调用 Novel-Control-Station-Skill。NCS 必须读取 `.webnovel/tmp/ncs-bridge/` 下的 00-09 标准文件、`control-cards/{NN}-control-card.md` 和 `chapters/` 最近章节后再起草。

输出先落到 `.webnovel/tmp/ncs-bridge/chapters/{NN}-<title>.md`，再适配回 `正文/第{NNNN}章-{title}.md`。禁止绕过桥接包只用单章提示直接写。

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

### Step 4：NCS 复查与轻润色

加载 `../novel-station-adapter/SKILL.md`、`../webnovel-write/references/polish-guide.md`、`../webnovel-write/references/writing/typesetting.md`、`../webnovel-write/references/style-adapter.md`。

顺序：修复非 blocking issue → 调用 Novel-Control-Station-Skill 的 `polish` / authenticity pass → 风格适配 → 排版 → NCS 终检。

### Step 5：提交

#### 5.1 Data Agent 提取事实

Task 调用 `data-agent`，产出 review_results / fulfillment_result / disambiguation_result / extraction_result 四份 JSON。

#### 5.2 CHAPTER_COMMIT

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter {chapter_num} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

#### 5.3 验证投影

projection_status 五项（state/index/summary/memory/vector）全部 done 或 skipped。

### Step 6：Git 备份

```bash
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第{chapter_num}章: {title}"
```

## 充分性闸门

1. 章节号已解析
2. 合同文件存在且非空
3. 正文文件存在且非空
4. 审查已落库（`--minimal` 除外）
5. accepted CHAPTER_COMMIT，projection 五项 done/skipped
6. chapter_status=committed（projection 自动推进）

## 推荐用法

```bash
/webnovel-writer:webnovel-chapter 1
/webnovel-writer:webnovel-chapter 12
/webnovel-writer:webnovel-chapter
```

其中前两种都是直接数字；最后一种默认写下一章。
