---
name: no-webnovel-write
description: Use when writing, continuing, revising, polishing, or reviewing a webnovel-writer chapter with the sibling Novel-Control-Station-Skill/No as the prose engine, while preserving the existing dashboard, character cards, timeline, story-system, and data commit flow.
---

# No Webnovel Write

## Intent

Use No/NCS only as the prose engine. Keep webnovel-writer as the control station for:

- project binding and book switching
- dashboard and menus
- character cards and setting files
- outlines, timelines, beat sheets, summaries, memory, and index.db
- reviewer, data-agent, chapter-commit, and projection updates

Do not replace the existing panel or information-card system.

## Usage And Update Rules

Use this skill when the user asks to write, continue, revise, polish, or review a `webnovel-writer` manuscript chapter, for example: `写第X章`, `继续下一章`, `重写第X章`, `修正文风但不改设定`.

Do not use this skill for dashboard UI work, browser login/debugging, publishing-panel fixes, or file-browser fixes unless the same request also writes or revises chapter prose.

Update this skill when a stable project-wide writing workflow changes:

- required source files, scripts, gates, or checklists change
- No/NCS bridge, preflight, chapter-commit, or projection flow changes
- source-of-truth paths move
- new mandatory validation rules are added
- recurring review failures reveal a reusable rule
- a book-specific rule becomes stable enough to belong in that book's local skill

Do not update this skill for one-off preferences or temporary chapter notes. Put those in the active book's notes, checklist, or local `.codex/skills/no-webnovel-write/SKILL.md`.

After updating this skill:

- keep `SKILL.md` concise; do not add extra README/CHANGELOG files
- verify frontmatter `name` and `description` still describe the trigger accurately
- check referenced required files/scripts exist, or mark them clearly as conditional
- if `agents/openai.yaml` exists, ensure it still matches `SKILL.md`
- when relevant, run `preflight` and `where`
- confirm the No/NCS bridge and post-chapter update flow are still preserved

## Required Source

Load the sibling No skill before drafting:

`/Users/liangfushou/project/小说/new/Novel-Control-Station-Skill/SKILL.md`

For de-AI cleanup, load only when needed:

`/Users/liangfushou/project/小说/new/Novel-Control-Station-Skill/references/authenticity-and-de-ai-pass.md`

If the active book contains these files, load them before the final polish pass:

- `.webnovel/anti_ai_rewrite_manual.md`
- `.webnovel/anti_ai_checklist.md`
- `.webnovel/post_chapter_update_checklist.md`
- `大纲/番茄逐章爽点规格.md`
- `大纲/第7章后番茄重写总纲.md`
- `大纲/前期爽点重写方案.md`
- `大纲/全书番茄爽点总纲.md`
- `大纲/爽点矩阵.md`
- `大纲/B路线伏笔总表.md`
- `大纲/第1卷-爽点伏笔对照表.md` or the matching current-volume爽点伏笔表
- `大纲/番茄标题简介卖点卡.md`, `大纲/标题简介卖点卡.md`, or an equivalent title/intro/selling-point card when writing, reviewing, or revising chapters 1-3
- `大纲/第1章开屏钩子卡.md` when writing, reviewing, or revising chapter 1
- `大纲/黄金三章作战卡.md` when writing, reviewing, or revising chapters 1-3
- `大纲/黄金五章强化卡.md` when writing, reviewing, or revising chapters 1-5

## Writing Workflow

1. Resolve the active book with the existing webnovel-writer CLI.

```bash
python -X utf8 webnovel-writer/scripts/webnovel.py --project-root "$PWD" preflight
python -X utf8 webnovel-writer/scripts/webnovel.py --project-root "$PWD" where
```

2. Determine the target chapter from the user request, or use `current_chapter + 1` from `.webnovel/state.json`.

3. Refresh the runtime contracts if the chapter contract is missing or stale. Preserve the original story-system chain. Do not draft from a previous chapter's contract.

4. Build the No bridge package before drafting.

```bash
python -X utf8 webnovel-writer/scripts/webnovel.py --project-root "$PROJECT_ROOT" ncs-bridge --chapter "$CHAPTER_NUM" --recent-chapters 3
```

5. Draft through No/NCS from:

- `.webnovel/tmp/ncs-bridge/00-project-overview.md`
- `.webnovel/tmp/ncs-bridge/01-theme-and-proposition.md`
- `.webnovel/tmp/ncs-bridge/02-worldbuilding.md`
- `.webnovel/tmp/ncs-bridge/03-cast-bible.md`
- `.webnovel/tmp/ncs-bridge/04-relationship-map.md`
- `.webnovel/tmp/ncs-bridge/05-main-plotlines.md`
- `.webnovel/tmp/ncs-bridge/06-foreshadow-ledger.md`
- `.webnovel/tmp/ncs-bridge/07-chapter-roadmap.md`
- `.webnovel/tmp/ncs-bridge/08-dynamic-state.md`
- `.webnovel/tmp/ncs-bridge/09-style-guide.md`
- `.webnovel/tmp/ncs-bridge/control-cards/<CHAPTER>-control-card.md`
- `.webnovel/tmp/ncs-bridge/chapters/`
- If present, the active book's `大纲/番茄逐章爽点规格.md`, especially when writing or rewriting chapter 9 onward.
- If present, the active book's `大纲/第7章后番茄重写总纲.md`, especially when rewriting chapter 7 onward.
- If present, the active book's `大纲/前期爽点重写方案.md`, especially for chapters 1-30.
- If present, the active book's `大纲/全书番茄爽点总纲.md`, `大纲/爽点矩阵.md`, and current-volume爽点伏笔表 before drafting any Fanqie-facing chapter.
- If present and the target is chapters 1-3, the active book's title/intro/selling-point card.
- If present and the target is chapter 1, the active book's `大纲/第1章开屏钩子卡.md`.
- If present and the target is chapters 1-3, the active book's `大纲/黄金三章作战卡.md`.
- If present and the target is chapters 1-5, the active book's `大纲/黄金五章强化卡.md`.

6. Put the accepted chapter back into the normal webnovel-writer manuscript path:

`正文/第NNNN章-标题.md`

7. Continue with the existing reviewer, data-agent, chapter-commit, projection, and dashboard flow. No/NCS must not write directly to `.webnovel/state.json` as the source of truth.

8. Before chapter commit, run the post-chapter update checklist. If the chapter changes any character, skill, item, timeline event, relationship, foreshadowing, result payoff, or world-state fact, update the corresponding cards/indexes before finalizing.

9. After every accepted chapter, update the skill/item timeline gate before declaring the chapter complete:

- Open or create the active book's `设定集/技能物品时间线.md`.
- Add or update the row/section for the target chapter.
- Record every skill or item that appears, changes state, changes owner, is consumed, is damaged, is unlocked, is sealed, is foreshadowed, or creates a future obligation.
- If no skill or item state changes occur, explicitly record `本章无技能/物品状态变化`.
- Do not leave middle-chapter gaps; if the current chapter exposes missing timeline entries for earlier accepted chapters, backfill them before finalizing.

10. After every accepted chapter, update the character-state gate before declaring the chapter complete:

- Open the active book's `设定集/主角卡.md` and relevant files under `设定集/角色库/`.
- Record changes in injury, location, known information, trust/enmity, faction stance, disguise, obligation, transaction, and relationship state.
- If no character state changes occur, explicitly record `本章无人物状态变化`.
- If an original-canon character acts beyond the current stage, record the chapter evidence and motivation instead of leaving it as unexplained OOC.

11. After every accepted chapter, update the result/foreshadowing gate before declaring the chapter complete:

- Check the chapter against the current-volume爽点伏笔表, `大纲/爽点矩阵.md`, and `大纲/B路线伏笔总表.md` when present.
- Record the chapter's visible result payoff in the summary, commit notes, review report, or checklist output. Do not put the words `爽点`, `结果爽`, `伏笔`, or `主线` into manuscript prose.
- For every planted, advanced, delayed, invalidated, or paid-off clue, update the foreshadowing ledger or the closest project equivalent.
- If the chapter has no visible reader reward, revise the chapter before accepting it.

12. After every accepted chapter, update the timeline/event gate before declaring the chapter complete:

- Update `大纲/剧情时间轴.md` or the story-system event log with chapter time, location, conflict, result, and changed world state.
- Update the matching `大纲/第X卷-时间线.md` when the chapter belongs to a planned volume.
- Update `设定集/同人分歧点.md` if the chapter changes, delays, accelerates, or preserves an original-canon event in a meaningful way.
- If no timeline/world-state change occurs, explicitly record `本章无时间线状态变化`.

13. Run the chapter artifact completeness gate before telling the user the chapter is finished. The accepted chapter must have the expected manuscript, summary, story-system chapter record, commit, event log, review result/report, projection/index updates, and all five post-chapter ledgers: character, skill, item, timeline, and result/foreshadowing. If any artifact is missing for the target chapter, create it through the normal CLI flow or report it as a blocking data gap.

14. Run the stale-review gate after every manuscript edit, anti-AI rewrite, or word-count repair. If the manuscript modification time is newer than the current review, metrics, commit, or projection artifacts, old scores and old accepted commits are invalid. Do not merely say the chapter "should be returned"; execute the return by writing `.webnovel/tmp/chNNNN_review_gate_status.md` with `review_gate: rewrite_required` or `review_gate: review_pending`, the stale artifact timestamps, and `accepted_commit_stale: true` when applicable. Until current reviewer/review-pipeline/data-agent/chapter-commit/projection artifacts are regenerated from the latest manuscript and pass thresholds, do not call the chapter complete, scored, accepted, or ready.

15. Review results generation: `review-pipeline` is a READ-ONLY command — it reads `.webnovel/tmp/review_results.json` and converts it to metrics for index.db. It does NOT generate review content. Before calling review-pipeline, you MUST first generate the review JSON yourself and write it to `.webnovel/tmp/review_results.json` with the correct format:
```json
{
  "chapter": CHAPTER_NUM,
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
  "问题清单": [{"severity": "minor", "问题": "..."}],
  "总结": "..."
}
```
The `chapter` field MUST match the current chapter number. If the file contains stale data from a previous chapter, overwrite it completely. Then call review-pipeline with `--save-metrics` to persist to index.db.

## Drafting Order

Use this order for every manuscript chapter:

1. Use No Webnovel Write as the main writing flow.
2. Draft from the bridge/context files and existing chapter contract.
3. Run a light anti-AI/authenticity pass after the draft.
4. The anti-AI pass may only change language, rhythm, dialogue naturalness, and paragraph texture.
5. The anti-AI pass must not change plot facts, character motivation, timeline, power/skill state, item ownership, foreshadowing state, or add new settings.
6. Re-check continuity after the anti-AI pass before committing.

## Fanqie Result-Satisfying Rules

For Fanqie-facing chapters, especially rewrites from chapter 9 onward, each chapter must close one visible reader reward before opening the next hook:

- Every chapter needs one `结果爽`: save someone, force back an enemy, win a trade, seize evidence, expose a lie, make a named character choose, kill/disable a threat, or turn a clue into leverage.
- A clue may not stay as quiet information for more than half a chapter. It must become enemy action, a living-person crisis, a trap, a transaction, a betrayal, or a pursuit.
- Do not end a chapter only with "a bigger secret". End with a near-term conflict the next chapter can immediately hit.
- Every 3 chapters need at least one hard conflict: pursuit, siege, ambush, trade betrayal, public pressure, named enemy action, or original-canon force entering.
- Every 5 chapters need at least one small climax: someone lives, dies, changes side, loses leverage, gets exposed, or pays a clear cost.
- Emotional chapters still need action payoff. A character should prove the emotional turn by doing something, not by explaining it.
- If a chapter lacks `结果爽`, revise before accepting; do not push the payoff to a later chapter.

## Golden Opening And Golden Three Gate

For chapters 1-3, do not treat outline/contract completion as acceptance. The opening package must create next-click desire.

Before drafting, reviewing, or revising chapters 1-3:

- Read title/package materials when present: title card, intro/selling-point card, chapter 1 hook card, golden three/five cards.
- Write one private/check-note line: `Readers came for X`.
- Ensure chapter 1 first screen delivers X through crisis, action, voice, or a sharp dilemma; do not open with explanation alone.
- If the title/intro promise and chapter 1 promise conflict, stop and either retitle/repackage or rewrite the opening before polishing prose.

Each of chapters 1-3 must have:

- one retellable visible result
- one pressure source that loses something, escalates, or makes a new move
- one protagonist card gained or preserved, with cost, debt, injury, exposure, or risk
- one next-chapter reason that is more concrete than "a bigger secret"
- one genre/high-heat anchor matching the book package

Golden three fail states:

- the protagonist only survives or escapes three times
- clues remain quiet information instead of becoming action, leverage, or danger
- chapter endings rely on abstract mystery rather than immediate conflict or a hot question
- high-heat characters, enemies, systems, or items appear but do not change on-page action
- the golden finger is explained but not paid off on-page
- the package says one book while the opening delivers another

Before accepting chapters 1-3, answer in notes/check output:

- `title/package promise:`
- `Ch1 next-click reason:`
- `Ch2 next-click reason:`
- `Ch3 next-click reason:`
- `visible result per chapter:`
- `mismatch/rewrite decision:`

## Manuscript Meta-Language Ban

`结果爽` is a drafting/checking concept, not manuscript prose. Put result-satisfying notes in summaries, checklists, reviews, or working notes only. Never write them into `正文/第NNNN章-标题.md`.

Ban authorial process/summary language in manuscript prose, including lines like:

- `这就是本章的结果`
- `这一轮残局被按住了`
- `这不是普通追杀`
- `这件事很小`
- `这句话比...更...`
- `这一下...`
- `制度压力`
- `正式升级`
- `主线/伏笔/爽点/结果爽`

Replace these with scene-visible consequences:

- who moves, stops, pays, bleeds, retreats, gives way, takes an item, loses an item, or changes stance
- what object changes state on-page
- what line of dialogue forces the next action
- what nearby character does differently after the payoff

Before accepting any chapter, run a manuscript scan for meta-language. If a sentence sounds like a chapter review, outline note, platform pacing diagnosis, or workflow annotation, remove it from正文 and rewrite it as action, dialogue, or concrete aftermath.

## Post-Chapter Update Requirements

After the accepted chapter is written, update every affected source of truth. Do not rely on the prose alone.

Completion definition: a chapter is not complete just because `正文/第NNNN章-标题.md` exists. It is complete only after the manuscript, summary, story-system artifacts, dashboard/index refresh sources, and these five ledgers are updated or explicitly marked unchanged:

- character ledger: 人物状态、关系、阵营、伤势、已知信息、选择变化
- skill ledger: 系统、词条、忍术、体术、限制、冷却、反噬、升级
- item ledger: 道具、证物、持有人、位置、损坏、消耗、转移、遗失
- timeline ledger: `大纲/剧情时间轴.md`, matching volume timeline, story-system events, original-canon divergence
- result/foreshadowing ledger: 本章可复述结果、打脸/反打/夺证/救人/逼退等兑现情况、伏笔新增/推进/回收/延期

Required checks:

- character cards and character state
- relationships and relationship events
- skill cards, skill ownership, cooldown/limits, injuries, unlock state, and skill evolution
- item cards, item ownership, location, damage, consumption, transfer, loss, or unlock state
- `设定集/技能物品时间线.md` for every accepted chapter, even when there is no change
- if a new skill or item enters正文 from plan state, create or update its card before finalizing
- outline/timeline/event logs if the chapter advances or changes planned events
- foreshadowing ledger if a clue is planted, paid off, delayed, or invalidated
- current-volume爽点伏笔表 and `大纲/爽点矩阵.md` when present; if the planned result changes, update the plan instead of leaving it stale
- chapter summary, `.story-system/chapters`, `.story-system/commits`, `.story-system/events`, `.story-system/reviews`, memory, index.db, state.json, and projection outputs through the normal webnovel-writer commit flow

Rules:

- If nothing changed, explicitly record "no state update needed" for the affected ledger in the working notes/check result.
- For skill/item timeline specifically, do not rely only on working notes; the chapter entry must exist in `设定集/技能物品时间线.md` or the project's equivalent timeline file.
- For result/foreshadowing specifically, do not rely only on memory; the chapter's visible result and clue state must be present in the summary, review/check output, story-system event, or the active foreshadowing table.
- Do not mark a chapter complete when正文 exists but story-system commit/events/review/projection files are missing.
- Do not mark a chapter complete when any of the five ledgers is missing for the target chapter.
- Never silently change a card to make the new prose fit; if the prose contradicts a card, fix the prose or surface the conflict.
- Anti-AI cleanup must never change state-bearing facts after this check without re-running the check.

## Dashboard Refresh Source Rules

The dashboard must remain data-driven. When adding chapters, summaries, or setting cards, keep the current project conventions so refresh buttons and page reloads can pick them up automatically:

- chapter files: `正文/第NNNN章-标题.md`
- chapter summaries: `.webnovel/summaries/chNNNN.md`
- protagonist source: `设定集/主角卡.md`, with either `# 主角卡：姓名` or `姓名：姓名`
- setting/card sources: `设定集/角色库/`, `设定集/技能卡/`, `设定集/物品库/`, and `设定集/其他设定/`
- generated/index sources: `.webnovel/index.db`, story events, state changes, memory, and projection outputs

Rules:

- Do not hard-code book-specific protagonist names, chapter ranges, entity counts, or missing-chapter ranges in dashboard code or skill instructions.
- If a dashboard fallback is needed, derive it from `主角卡.md`, project config/state, chapter filenames, summaries, setting cards, or index data.
- After adding or revising a chapter, update the summary/card/index/projection flow before judging dashboard charts.
- If the dashboard still looks stale, refresh the page first; for entities use the panel's `刷新实体` button.

## Anti-AI Taste Rules

Prefer No's authenticity pass over the old rewrite style. Preserve scene meaning, but reduce:

- generic emotional summaries
- tidy three-part explanatory prose
- slogans, false depth, and conclusion sentences
- analysis-tone words in narration
- samey dialogue and over-polished speaker rhythm
- decorative blank-line chopping

Do not add fake "human flavor" memories just to look less AI. Make the scene more concrete, pressured, and voiced.

## Early Hook Rules

For chapters 1-30, do not let the chapter become pure archive investigation. A clue must quickly turn into pressure, pursuit, betrayal, a visible choice, or an original-canon callback. If the active book has `大纲/前期爽点重写方案.md`, obey it as a first-volume pacing constraint.
