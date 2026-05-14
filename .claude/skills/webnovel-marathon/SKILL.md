---
name: webnovel-marathon
description: 串行批量写章流水线。指定章节范围后全自动循环：写稿→DS润色→番茄排版→数据更新→落库→下一章，中间不需要用户确认。
allowed-tools: Read Write Edit Bash Agent Skill Task
---

# webnovel-marathon：串行批量写章流水线

## 用法

```bash
/webnovel-marathon 1-10      # 写第1章到第10章
/webnovel-marathon 5-5       # 只写第5章
/webnovel-marathon 3         # 从第3章写到大纲末尾
```

## 核心原则

- **全自动串行**：每章完成后自动进入下一章，不等用户确认
- **每章独立完整**：每章必须完成写稿+润色+数据更新+落库才算完成，才能进入下一章
- **失败就停**：任何步骤失败，停在当前章，报告失败原因，不跳过继续
- **数据更新不能省**：伏笔/人物/技能物品/时间轴必须在每章落库前更新完

---

## 执行流程

### 准备：预检

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

### 准备：解析章节范围

- `1-10` → 第1章到第10章
- `5` → 从第5章到大纲末尾（读 state.json 的 total_chapters 或 volume 末章）
- `5-5` → 只写第5章

### 对每章执行以下串行步骤：

---

#### Step 1：刷新合同和桥接包

```bash
GENRE="$(python -X utf8 -c "import json; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('project_info',{}).get('genre',''))")"
python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  story-system "第${CHAPTER_NUM}章章纲目标" --genre "${GENRE}" --chapter ${CHAPTER_NUM} --persist --emit-runtime-contracts --format both
python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${PROJECT_ROOT}" \
  ncs-bridge --chapter "${CHAPTER_NUM}" --recent-chapters 3
```

---

#### Step 1.5：知识库查询（index.db + vectors.db）

如果 `.webnovel/index.db` 和 `.webnovel/vectors.db` 存在且非空，必须在写作前查询：

```bash
# 查询本章出场角色的最新状态
python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  knowledge "第${CHAPTER_NUM}章相关角色状态"

# RAG 语义检索：前文是否有类似场景/对话（避免重复）
python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  rag "本章核心场景关键词"

# 查询相关伏笔当前状态
python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  index query "伏笔"
```

查询目的：
- 确认出场角色的位置、伤势、已知信息（防止写出矛盾）
- 检查前文是否已有类似场景或对话（防止重复）
- 确认相关伏笔状态（已种/已收/延期，防止遗漏或重复回收）
- 长篇（10章+）时此步骤为**必须**，短篇（≤10章）为建议

如果 index.db/vectors.db 不存在（如第一章），跳过此步骤。

---

#### Step 2：NCS 主写作（no-webnovel-write）

加载 `/Users/liangfushou/project/小说/new/Novel-Control-Station-Skill/SKILL.md`，按 no-webnovel-write 的写作流程起草本章。

必须读取：
- `.webnovel/tmp/ncs-bridge/` 下的 00-09 标准文件
- `.webnovel/tmp/ncs-bridge/control-cards/{NN}-control-card.md`
- 章节合同、开屏钩子卡（第1-3章）、黄金三章作战卡（第1-3章）
- Step 1.5 的知识库查询结果（如有）

输出写入：`正文/第{NNNN}章-{title}.md`

---

#### Step 3：DS 润色（deepseek-deslop）

读取 `webnovel-writer/skills/webnovel-write/references/deepseek-universal-polish-v2.yaml`，对 Step 2 输出执行：
1. 删除 AI 填充词、模板段落、元说明
2. 格式规范（引号、省略号、破折号）
3. 字典替换
4. 语义重写（消除AI腔、增强文学质感、保留原意）

结果写回 `正文/第{NNNN}章-{title}.md`（覆盖）

---

#### Step 4：番茄排版（webnovel-deslop Stage 2）

读取 `webnovel-writer/skills/webnovel-write/references/tomato-mobile-formatting.yaml`，对 Step 3 输出执行：
1. 对话孤立（前后双换行）
2. 文字墙粉碎（40字强制换行）
3. 删除番茄禁忌词
4. 节奏提速替换
5. 章末留白

结果写回 `正文/第{NNNN}章-{title}.md`（覆盖）

---

#### Step 5：数据更新（全量，不能省）

**重要区分**：chapter-commit 的 extraction_result.json 是给系统落库用的，不等于手动更新 markdown 文件。以下五项必须直接编辑对应的 .md 文件，不能只生成 JSON 就算完成。

用 Agent 执行以下五项更新，每项必须完成或明确记录"本章无变化"：

**5.0 读取角色卡（写章前必做）**
在 Step 2 NCS 写作之前，读取本章涉及角色的独立人物卡（`设定集/角色库/主要角色/`、`设定集/角色库/次要角色/`、`设定集/角色库/反派角色/`），确认：
- 每个角色的生死状态、当前位置、立场、已知信息
- 原作对照部分：防止让已死角色出场或做出不符合时间线的事
- 若角色卡标注"死亡"或"不在此地"，不得在本章让其出场（除非大纲明确安排其回归/复活）

**5.1 人物状态更新（含独立角色卡）**
读取本章正文，对照 `设定集/主角卡.md` 和 `设定集/角色库/` 下相关文件，更新：
- 伤势、位置、已知信息、信任/敌意、阵营立场、伪装、义务、交易、关系变化
- **必须更新涉及角色的独立人物卡**（`设定集/角色库/` 下对应文件的"当前状态"和"关键事件记录"部分）
- 若无变化，在文件末尾追加：`<!-- 第{N}章：无人物状态变化 -->`

**5.2 技能物品时间线更新**
读取本章正文，更新 `设定集/技能物品时间线.md`：
- 记录本章出现、变化、转移、消耗、解锁、封印的技能和物品
- 若无变化，追加：`| 第{N}章 | 无技能/物品状态变化 |`

**5.3 伏笔更新**
读取本章正文，对照 `大纲/第{X}卷-伏笔总表.md`，更新：
- 新埋伏笔、推进中的伏笔、已回收的伏笔、延期的伏笔
- 若无变化，追加记录

**5.4 时间轴更新**
更新 `大纲/剧情时间轴.md` 和对应卷时间线：
- 记录本章时间、地点、冲突、结果、世界状态变化
- 若本章改变/延迟/加速了原作事件，更新 `设定集/同人分歧点.md`

**5.5 大纲爽点对照更新**
对照 `大纲/第{X}卷-爽点伏笔对照表.md`，记录本章的可复述结果（打脸/夺证/救人/逼退等兑现情况）

---

#### Step 6：审查落库

分两步完成：

**Step 6.1：AI 生成审查 JSON**

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

审查维度评分标准：
- 90+：该维度表现优秀，无明显问题
- 80-89：合格，有小瑕疵但不影响阅读
- 70-79：有明显问题需要注意
- <70：严重问题，建议修改

overall_score = 六个维度的平均分（四舍五入取整）

**重要**：`review_results.json` 的 `chapter` 字段必须等于当前章号。如果文件里是旧章数据，必须覆盖。

**Step 6.2：review-pipeline 转化为 metrics 并落库**

`review-pipeline` 命令只负责**读取** review_results.json 并转化为 metrics 写入 index.db，它不生成审查内容。

```bash
python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline \
  --chapter ${CHAPTER_NUM} \
  --review-results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --metrics-out "${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json" \
  --report-file "审查报告/第${CHAPTER_NUM}章审查报告.md" \
  --save-metrics
```

注意：加 `--save-metrics` 直接写入 index.db，省去单独调用。

---

#### Step 7：chapter-commit 落库

用 Agent 执行 data-agent 提取事实，产出四份 JSON，然后：

```bash
python -X utf8 "${WORKSPACE_ROOT}/webnovel-writer/scripts/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter ${CHAPTER_NUM} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

---

#### Step 8：Git 备份

```bash
cd "${PROJECT_ROOT}"
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第${CHAPTER_NUM}章: ${CHAPTER_TITLE}"
```

---

#### Step 9：进入下一章

更新循环计数器，重复 Step 1-8，直到范围结束。

---

## 充分性闸门（每章必须全部通过才能进入下一章）

1. 正文文件存在且字数 > 1000
2. DS 润色已完成（无 AI 填充词残留）
3. 番茄排版已完成
4. 五项数据更新全部完成或明确记录"无变化"
5. review_results.json 已生成且 blocking_count = 0
6. chapter-commit 已接受
7. git commit 已完成

---

## 失败处理

- 任何步骤失败 → 停止循环，报告：当前章节号、失败步骤、失败原因
- 不跳过失败章节继续写下一章
- 用户修复后可以用 `/webnovel-marathon {N}-{end}` 从失败章节重新开始

---

## 进度报告格式

每章完成后输出一行：
```
✓ 第{N}章「{title}」完成 | {字数}字 | 伏笔{新增/推进/回收}N条 | 人物状态已更新
```

全部完成后输出：
```
marathon 完成：第{start}章 → 第{end}章，共{N}章，总字数{X}字
```
