---
name: no-webnovel-write
description: Use when writing or continuing a webnovel-writer chapter with the sibling Novel-Control-Station-Skill/No as the prose engine, while preserving the existing dashboard, character cards, timeline, story-system, and data commit flow.
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

## Required Source

Load the sibling No skill before drafting:

`/Users/liangfushou/project/小说/new/Novel-Control-Station-Skill/SKILL.md`

For de-AI cleanup, load only when needed:

`/Users/liangfushou/project/小说/new/Novel-Control-Station-Skill/references/authenticity-and-de-ai-pass.md`

If the active book contains these files, load them before the final polish pass:

- `.webnovel/anti_ai_rewrite_manual.md`
- `.webnovel/anti_ai_checklist.md`
- `.webnovel/post_chapter_update_checklist.md`
- `大纲/前期爽点重写方案.md`

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
- If present, the active book's `大纲/前期爽点重写方案.md`, especially for chapters 1-30.

6. Put the accepted chapter back into the normal webnovel-writer manuscript path:

`正文/第NNNN章-标题.md`

7. Continue with the existing reviewer, data-agent, chapter-commit, projection, and dashboard flow. No/NCS must not write directly to `.webnovel/state.json` as the source of truth.

8. Before chapter commit, run the post-chapter update checklist. If the chapter changes any character, skill, item, timeline event, relationship, foreshadowing, or world-state fact, update the corresponding cards/indexes before finalizing.

## Drafting Order

Use this order for every manuscript chapter:

1. Use No Webnovel Write as the main writing flow.
2. Draft from the bridge/context files and existing chapter contract.
3. Run a light anti-AI/authenticity pass after the draft.
4. The anti-AI pass may only change language, rhythm, dialogue naturalness, and paragraph texture.
5. The anti-AI pass must not change plot facts, character motivation, timeline, power/skill state, item ownership, foreshadowing state, or add new settings.
6. Re-check continuity after the anti-AI pass before committing.

## Post-Chapter Update Requirements

After the accepted chapter is written, update every affected source of truth. Do not rely on the prose alone.

Required checks:

- character cards and character state
- relationships and relationship events
- skill cards, skill ownership, cooldown/limits, injuries, unlock state, and skill evolution
- item cards, item ownership, location, damage, consumption, transfer, loss, or unlock state
- skill/item timeline if any skill or object appears, changes hands, changes state, or creates a future obligation
- if a new skill or item enters正文 from plan state, create or update its card before finalizing
- outline/timeline/event logs if the chapter advances or changes planned events
- foreshadowing ledger if a clue is planted, paid off, delayed, or invalidated
- chapter summary, memory, index.db, state.json, and projection outputs through the normal webnovel-writer commit flow

Rules:

- If nothing changed, explicitly record "no state update needed" in the working notes/check result.
- Never silently change a card to make the new prose fit; if the prose contradicts a card, fix the prose or surface the conflict.
- Anti-AI cleanup must never change state-bearing facts after this check without re-running the check.

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
