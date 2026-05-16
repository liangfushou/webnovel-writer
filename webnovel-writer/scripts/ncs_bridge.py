#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from project_locator import resolve_project_root


STANDARD_FILES = (
    "00-project-overview.md",
    "01-theme-and-proposition.md",
    "02-worldbuilding.md",
    "03-cast-bible.md",
    "04-relationship-map.md",
    "05-main-plotlines.md",
    "06-foreshadow-ledger.md",
    "07-chapter-roadmap.md",
    "08-dynamic-state.md",
    "09-style-guide.md",
)


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _dump_json(value: Any) -> str:
    if value is None or value == "":
        return "（暂无）"
    return json.dumps(value, ensure_ascii=False, indent=2)


def _project_info(state: dict[str, Any]) -> dict[str, Any]:
    info = dict(state.get("project_info") or state.get("project") or {})
    if info:
        return info
    return {
        "title": state.get("book_title") or state.get("title") or state.get("book_id") or "",
        "genre": state.get("genre") or state.get("book_genre") or "",
        "target_words": state.get("target_words") or state.get("target_word_count") or "",
        "target_chapters": state.get("target_chapters") or state.get("total_planned_chapters") or "",
    }


def _current_chapter(state: dict[str, Any]) -> int:
    progress = state.get("progress") or {}
    try:
        return int(progress.get("current_chapter") or state.get("current_chapter") or state.get("last_completed_chapter") or 0)
    except (TypeError, ValueError):
        return 0


def _chapter_arg(state: dict[str, Any], chapter: int | None) -> int:
    if chapter and chapter > 0:
        return chapter
    return _current_chapter(state) + 1


def _volume_for_chapter(state: dict[str, Any], chapter: int) -> int:
    progress = state.get("progress") or {}
    planned = progress.get("volumes_planned") or []
    for item in planned:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("chapters_range") or "")
        match = re.search(r"(\d+)\D+(\d+)", raw)
        if not match:
            continue
        start, end = int(match.group(1)), int(match.group(2))
        if start <= chapter <= end:
            try:
                return int(item.get("volume") or 1)
            except (TypeError, ValueError):
                return 1
    return max(1, (chapter - 1) // 50 + 1)


def _route_cutover_invalidates_previous_artifacts(state: dict[str, Any], chapter: int) -> bool:
    text = "\n".join(
        str(state.get(key) or "")
        for key in ("current_focus", "next_action", "notes")
    )
    if "B路线" not in text:
        return False
    if "旧第" not in text or "不再" not in text:
        return False
    match = re.search(r"旧第\s*(\d+)\s*[-—至到]\s*(\d+)\s*章", text)
    if not match:
        return False
    start, end = int(match.group(1)), int(match.group(2))
    return start <= chapter <= end


def _volume_from_outline_headers(project_root: Path, chapter: int) -> int | None:
    outline_dir = project_root / "大纲"
    if not outline_dir.is_dir():
        return None
    for path in sorted(outline_dir.glob("第*卷-详细大纲.md")):
        volume_match = re.search(r"第(\d+)卷", path.name)
        if not volume_match:
            continue
        text = _read_text(path)
        chapter_nums = [int(item) for item in re.findall(r"^##\s*第(\d+)章", text, flags=re.MULTILINE)]
        if chapter in chapter_nums:
            return int(volume_match.group(1))
        if chapter_nums and min(chapter_nums) <= chapter <= max(chapter_nums):
            return int(volume_match.group(1))
    return None


def _first_existing(project_root: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = project_root / rel
        if path.is_file():
            return path
    return None


def _outline_files(project_root: Path, volume: int) -> list[Path]:
    outline_dir = project_root / "大纲"
    if not outline_dir.is_dir():
        return []
    volume_patterns = [
        f"*第{volume}章开屏钩子*.md",
        f"*第{volume:04d}章开屏钩子*.md",
        f"*第{volume}卷*时间线*.md",
        f"*第{volume:03d}卷*时间线*.md",
        f"*{volume}卷*时间线*.md",
        f"*第{volume}卷*节拍*.md",
        f"*第{volume:03d}卷*节拍*.md",
        f"*{volume}卷*节拍*.md",
        f"*第{volume}卷*伏笔*.md",
        f"*第{volume:03d}卷*伏笔*.md",
        f"*{volume}卷*伏笔*.md",
        f"*第{volume}卷*详细大纲*.md",
        f"*第{volume:03d}卷*详细大纲*.md",
        f"*{volume}卷*详细*.md",
    ]
    fallback_patterns = [
        "*时间线*.md",
        "*节拍*.md",
        "*伏笔*.md",
        "*详细大纲*.md",
        "*章纲*.md",
    ]

    def collect(patterns: list[str]) -> list[Path]:
        seen: set[Path] = set()
        result: list[Path] = []
        for pattern in patterns:
            for path in sorted(outline_dir.glob(pattern)):
                file_volume = re.search(r"第(\d+)卷", path.name)
                if file_volume and int(file_volume.group(1)) != volume:
                    continue
                if path not in seen and path.is_file():
                    seen.add(path)
                    result.append(path)
        return result

    result = collect(volume_patterns)
    if result:
        return result
    return collect(fallback_patterns)


def _outline_files_legacy(project_root: Path, volume: int) -> list[Path]:
    outline_dir = project_root / "大纲"
    if not outline_dir.is_dir():
        return []
    seen: set[Path] = set()
    result: list[Path] = []
    for pattern in ("*时间线*.md", "*节拍*.md", "*伏笔*.md", "*详细大纲*.md", "*章纲*.md"):
        for path in sorted(outline_dir.glob(pattern)):
            file_volume = re.search(r"第(\d+)卷", path.name)
            if file_volume and int(file_volume.group(1)) != volume:
                continue
            if path not in seen and path.is_file():
                seen.add(path)
                result.append(path)
    return result


def _extract_chapter_section(text: str, chapter: int) -> str:
    heading = re.compile(rf"^##\s*第0*{chapter}章[^\n]*", flags=re.MULTILINE)
    match = heading.search(text)
    if not match:
        return ""
    next_heading = re.compile(r"^##\s*第\d+章[^\n]*", flags=re.MULTILINE)
    next_match = next_heading.search(text, match.end())
    end = next_match.start() if next_match else len(text)
    return text[match.start() : end].strip()


def _chapter_outline_section(project_root: Path, chapter: int, volume: int) -> str:
    files = _outline_files(project_root, volume)
    files = sorted(files, key=lambda path: (0 if "详细大纲" in path.name or "章纲" in path.name else 1, path.name))
    for path in files:
        section = _extract_chapter_section(_read_text(path), chapter)
        if section:
            return f"## {path.name}\n\n{section}"
    return ""


def _latest_files(directory: Path, pattern: str, limit: int) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob(pattern), key=lambda p: p.name)[-limit:]


def _chapter_number_from_path(path: Path) -> int | None:
    name = path.name
    patterns = (
        r"ch(?:apter)?[_-]?0*(\d+)",
        r"第0*(\d+)章",
        r"^0*(\d+)[-_]",
    )
    for pattern in patterns:
        match = re.search(pattern, name, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _chapter_status(state: dict[str, Any], chapter: int) -> str:
    progress = state.get("progress") or {}
    chapter_status = progress.get("chapter_status") or {}
    if isinstance(chapter_status, dict):
        return str(chapter_status.get(str(chapter)) or chapter_status.get(chapter) or "")
    return ""


def _latest_files_before_chapter(directory: Path, pattern: str, chapter: int, limit: int, state: dict[str, Any] | None = None) -> list[Path]:
    if not directory.is_dir() or limit <= 0:
        return []
    numbered: list[tuple[int, str, Path]] = []
    for path in directory.glob(pattern):
        number = _chapter_number_from_path(path)
        if number is None or number >= chapter:
            continue
        if state is not None and "rewrite_pending_old_route_invalid" in _chapter_status(state, number):
            continue
        numbered.append((number, path.name, path))
    return [path for _, _, path in sorted(numbered)[-limit:]]


def _read_joined(paths: list[Path], *, empty: str = "（暂无）") -> str:
    chunks = []
    for path in paths:
        text = _read_text(path).strip()
        if text:
            chunks.append(f"## {path.name}\n\n{text}")
    return "\n\n".join(chunks) if chunks else empty


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}


def _select_rows(conn: sqlite3.Connection, table: str, columns: list[str], *, where: str = "", order: str = "", limit: int = 20) -> list[dict[str, Any]]:
    available = _table_columns(conn, table)
    selected = [column for column in columns if column in available]
    if not selected:
        return []
    sql = f"SELECT {', '.join(selected)} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    sql += f" LIMIT {int(limit)}"
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _order_clause(columns: set[str], candidates: list[str]) -> str:
    return ", ".join(candidate for candidate in candidates if candidate.split()[0] in columns)


def _snapshot_has_rows(snapshot: dict[str, Any] | None) -> bool:
    if not isinstance(snapshot, dict):
        return False
    return any(isinstance(value, list) and bool(value) for value in snapshot.values())


def _merge_index_snapshots(primary: dict[str, Any] | None, legacy: dict[str, Any] | None) -> dict[str, Any] | None:
    if not primary:
        return legacy
    if not legacy:
        return primary

    merged = dict(primary)
    for key, value in legacy.items():
        if key not in merged or not merged.get(key):
            merged[key] = value
    if _snapshot_has_rows(legacy):
        merged["legacy_root_index"] = legacy
    return merged


def _read_index_snapshot_from_db(db_path: Path, chapter: int) -> dict[str, Any] | None:
    if not db_path.is_file():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        entities_columns = _table_columns(conn, "entities")
        entity_where = "is_archived = 0" if "is_archived" in entities_columns else ""
        entity_order = _order_clause(entities_columns, ["is_protagonist DESC", "last_appearance DESC", "canonical_name ASC", "id ASC"])

        state_columns = _table_columns(conn, "state_changes")
        state_where = f"chapter <= {int(chapter)}" if "chapter" in state_columns else ""
        state_order = _order_clause(state_columns, ["chapter DESC", "id DESC"])

        rel_event_columns = _table_columns(conn, "relationship_events")
        rel_event_where = f"chapter <= {int(chapter)}" if "chapter" in rel_event_columns else ""
        rel_event_order = _order_clause(rel_event_columns, ["chapter DESC", "id DESC"])

        relationship_columns = _table_columns(conn, "relationships")
        relationship_where = f"chapter <= {int(chapter)}" if "chapter" in relationship_columns else ""
        relationship_order = _order_clause(relationship_columns, ["chapter DESC", "id DESC"])

        return {
            "entities": _select_rows(
                conn,
                "entities",
                ["id", "name", "canonical_name", "type", "tier", "description", "desc", "current_json", "source_file", "first_appearance", "last_appearance", "is_protagonist"],
                where=entity_where,
                order=entity_order,
                limit=40,
            ),
            "recent_state_changes": _select_rows(
                conn,
                "state_changes",
                ["entity_id", "field", "old_value", "new_value", "reason", "chapter"],
                where=state_where,
                order=state_order,
                limit=40,
            ),
            "recent_relationship_events": _select_rows(
                conn,
                "relationship_events",
                ["from_entity", "to_entity", "type", "relationship_type", "action", "description", "chapter", "evidence"],
                where=rel_event_where,
                order=rel_event_order,
                limit=40,
            ),
            "relationships": _select_rows(
                conn,
                "relationships",
                ["from_entity", "to_entity", "source_name", "target_name", "type", "relationship_type", "relation_type", "status", "description", "notes", "chapter"],
                where=relationship_where,
                order=relationship_order,
                limit=40,
            ),
            "character_state": _select_rows(
                conn,
                "character_state",
                ["character_name", "volume_no", "chapter_no", "physical_state", "mental_state", "faction", "known_info", "power_level", "notes"],
                order=_order_clause(_table_columns(conn, "character_state"), ["chapter_no DESC", "id DESC"]),
                limit=40,
            ),
            "timeline_events": _select_rows(
                conn,
                "timeline_events",
                ["volume_no", "chapter_no", "event_name", "event_type", "summary", "canon_status", "consequences"],
                order=_order_clause(_table_columns(conn, "timeline_events"), ["chapter_no DESC", "id DESC"]),
                limit=40,
            ),
            "foreshadows": _select_rows(
                conn,
                "foreshadows",
                ["name", "introduced_chapter", "status", "description", "planned_resolution"],
                order=_order_clause(_table_columns(conn, "foreshadows"), ["introduced_chapter DESC", "id DESC"]),
                limit=40,
            ),
            "continuity_rules": _select_rows(
                conn,
                "continuity_rules",
                ["rule_name", "rule_text", "priority"],
                order=_order_clause(_table_columns(conn, "continuity_rules"), ["priority DESC", "id ASC"]),
                limit=40,
            ),
            "chapter_index": _select_rows(
                conn,
                "chapter_index",
                ["chapter_no", "title", "volume_no", "summary", "contract_file", "commit_file", "status"],
                where=f"chapter_no <= {int(chapter)}" if "chapter_no" in _table_columns(conn, "chapter_index") else "",
                order=_order_clause(_table_columns(conn, "chapter_index"), ["chapter_no DESC"]),
                limit=20,
            ),
        }
    finally:
        conn.close()


def _read_index_snapshot(project_root: Path, chapter: int) -> dict[str, Any] | None:
    standard = _read_index_snapshot_from_db(project_root / ".webnovel" / "index.db", chapter)
    legacy = _read_index_snapshot_from_db(project_root / "index.db", chapter)
    if _snapshot_has_rows(standard) and not _snapshot_has_rows(legacy):
        return standard
    if _snapshot_has_rows(legacy):
        return _merge_index_snapshots(standard, legacy)
    return standard or legacy


def _read_knowledge_files(project_root: Path, *, limit: int = 20) -> str:
    knowledge_dir = project_root / ".webnovel" / "knowledge"
    if not knowledge_dir.is_dir():
        return "（暂无 knowledge 文件目录）"
    paths = sorted(
        path for path in knowledge_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".txt"}
    )[:limit]
    return _read_joined(paths, empty="（暂无 knowledge 文件）")


def _story_json(project_root: Path, kind: str, chapter: int | None = None, volume: int | None = None) -> Any:
    story_root = project_root / ".story-system"
    if kind == "master":
        return _read_json(story_root / "MASTER_SETTING.json")
    if kind == "anti":
        return _read_json(story_root / "anti_patterns.json")
    if kind == "chapter" and chapter is not None:
        for name in (
            f"chapter_{chapter:03d}.json",
            f"chapter_{chapter:03d}_contract.json",
            f"chapter_{chapter:03d}.contract.json",
        ):
            payload = _read_json(story_root / "chapters" / name)
            if payload is not None:
                return payload
        return None
    if kind == "review" and chapter is not None:
        for name in (
            f"chapter_{chapter:03d}.review.json",
            f"chapter_{chapter:03d}_review.json",
        ):
            payload = _read_json(story_root / "reviews" / name)
            if payload is not None:
                return payload
        return None
    if kind == "volume" and volume is not None:
        return _read_json(story_root / "volumes" / f"volume_{volume:03d}.json")
    return None


def _render_project_overview(project_root: Path, state: dict[str, Any]) -> str:
    info = _project_info(state)
    total_words = info.get("target_words") or info.get("target_word_count") or ""
    total_chapters = info.get("target_chapters") or ""
    idea_bank = _read_json(project_root / ".webnovel" / "idea_bank.json")
    outline = _read_text(project_root / "大纲" / "总纲.md")
    if str(state.get("current_stage") or "") == "rewrite_cutover":
        fanfic_plans = _read_joined(
            [
                path for path in (
                    project_root / "大纲" / "开头三章简介.md",
                    project_root / "大纲" / "黄金三章作战卡.md",
                    project_root / "大纲" / "B路线伏笔总表.md",
                    project_root / "大纲" / "竞品观察与避坑卡.md",
                )
                if path.is_file()
            ],
            empty="B路线重写切换中：以总纲、第1卷详细大纲、黄金三章作战卡和B路线伏笔为准。",
        )
    else:
        fanfic_plans = _read_joined(
            [
                path for path in (
                    project_root / "大纲" / "同人爽点模型.md",
                    project_root / "大纲" / "遗憾改写清单.md",
                    project_root / "大纲" / "竞品观察与避坑卡.md",
                    project_root / "大纲" / "黄金三章作战卡.md",
                    project_root / "大纲" / "原作事件保留表.md",
                    project_root / "大纲" / "原作人物交互规划.md",
                )
                if path.is_file()
            ],
            empty="（暂无同人专项规划）",
        )
    return f"""# 项目概览

**项目名称**: {info.get("title") or project_root.name}
**题材**: {info.get("genre") or ""}
**目标字数**: {total_words}
**目标章节数**: {total_chapters}
**发布模式**: 网文连载

## 核心设定与主线

{outline or "（暂无总纲）"}

## 同人专项规划

{fanfic_plans}

## 创意约束

```json
{_dump_json(idea_bank)}
```
"""


def _render_theme(state: dict[str, Any]) -> str:
    info = _project_info(state)
    return f"""# 主题与命题

## 目标读者与平台

- 目标读者：{info.get("target_reader") or ""}
- 平台：{info.get("platform") or ""}

## 核心卖点

{info.get("core_selling_points") or "（待补充）"}

## 主题约束

- 写作时优先保留人物欲望、代价、选择后果。
- 不用空泛主题句替代具体行动与场面压力。
"""


def _render_worldbuilding(project_root: Path, state: dict[str, Any], chapter: int) -> str:
    if _route_cutover_invalidates_previous_artifacts(state, chapter):
        worldview = "B路线重写切换中：当前主场从大蛇丸地下实验室、木叶边缘暗巷、中忍考试外围起步。旧开局世界观卡暂不注入 bridge。"
        power = "死劫改命系统：通过右眼提示当前死劫、命运死劫和奖励结算；改写死劫获得死劫点与忍道词条。系统不是全知剧透器，不送满级血继；关键使用会导致右眼流血、短暂失明、误判风险，并被大蛇丸或根部定位。"
        extra = "（B路线重写切换中：旧设定补充暂不注入 bridge，避免旧开局回流。）"
        lifecycle = "（B路线第1章尚未提交：旧技能物品时间线暂不注入 bridge；新正文提交后逐章重建。）"
        skill_cards = "（B路线第1章尚未提交：旧技能卡暂不批量注入 bridge；只使用死劫改命系统、忍道词条、当前章大纲、state.entity_state 与主角核心能力。）"
        item_cards = "（B路线第1章尚未提交：旧物品卡暂不批量注入 bridge；第1章可用物品以实验台束缚带、大蛇丸血样管、眼部查克拉记录、团藏密件等当前章大纲物品为准。）"
        fanfic_constraints = "B路线约束：大蛇丸、团藏、佐助前三章入场；第1章必须挖眼失败并炸蛇窟逃生；不得把旧开局支线当作前30章主卖点。"
    else:
        worldview = _read_text(project_root / "设定集" / "世界观.md")
        power = _read_text(project_root / "设定集" / "力量体系.md")
        extra = _read_joined(sorted((project_root / "设定集" / "其他设定").glob("*.md")) if (project_root / "设定集" / "其他设定").is_dir() else [])
        lifecycle = _read_text(project_root / "设定集" / "技能物品时间线.md")
        skill_cards = _read_joined(sorted((project_root / "设定集" / "技能卡").glob("*.md")) if (project_root / "设定集" / "技能卡").is_dir() else [], empty="（暂无技能卡/招式库）")
        item_cards = _read_joined(sorted((project_root / "设定集" / "物品库").glob("*.md")) if (project_root / "设定集" / "物品库").is_dir() else [], empty="（暂无物品卡/道具库）")
        fanfic_constraints = _read_joined(
            [
                path for path in (
                    project_root / "设定集" / "原作设定卡.md",
                    project_root / "设定集" / "原作时间线.md",
                    project_root / "设定集" / "同人分歧点.md",
                    project_root / "设定集" / "改写边界.md",
                    project_root / "设定集" / "OOC禁区.md",
                    project_root / "设定集" / "平台风格约束.md",
                    project_root / "设定集" / "原作人物交互规划.md",
                    project_root / "设定集" / "CP与感情线规则.md",
                )
                if path.is_file()
            ],
            empty="（暂无同人/原作约束）",
        )
    return f"""# 世界设定

## 世界观

{worldview or "（暂无）"}

## 力量体系

{power or "（暂无）"}

## 其他设定

{extra}

## 技能物品时间线

{lifecycle or "（暂无技能物品生命周期账本）"}

## 技能卡/招式库

{skill_cards}

## 物品卡/道具库

{item_cards}

## 同人/原作约束

{fanfic_constraints}
"""


def _render_cast_bible(project_root: Path, state: dict[str, Any], chapter: int) -> str:
    if _route_cutover_invalidates_previous_artifacts(state, chapter):
        protagonist = "雾原朔：现代穿越者，大蛇丸实验体逃杀线主角，死劫改命系统宿主；知道火影主要大事件，但被自己改动后的新死局会变形，不能靠完整剧情剧透速通。"
        heroine = "B路线前期无恋爱主卖点，感情线不得压过大蛇丸、团藏、佐助和中忍考试。"
        team = "前期关系核心：雾原朔与佐助是证据交易，不是信任；鸣人用行动介入但不能提前成熟；卡卡西观察边界。"
        antagonist = "卷一压迫源：大蛇丸挖眼与回收数据，团藏根部接收并封存实验体，音忍与根部围猎。"
    else:
        protagonist = _read_text(project_root / "设定集" / "主角卡.md")
        heroine = _read_text(project_root / "设定集" / "女主卡.md")
        team = _read_text(project_root / "设定集" / "主角组.md")
        antagonist = _read_text(project_root / "设定集" / "反派设计.md")
    character_dirs = [
        project_root / "设定集" / "角色库" / "主要角色",
        project_root / "设定集" / "角色库" / "次要角色",
        project_root / "设定集" / "角色库" / "反派角色",
    ]
    if _route_cutover_invalidates_previous_artifacts(state, chapter):
        library = "（B路线重写切换中：旧角色库暂不批量注入 bridge。当前章人物以大纲/第1卷-详细大纲.md 与 state.entity_state 为准。）"
    else:
        library_chunks: list[str] = []
        for directory in character_dirs:
            library_chunks.append(_read_joined(sorted(directory.glob("*.md")) if directory.is_dir() else [], empty=""))
        library = "\n\n".join(chunk for chunk in library_chunks if chunk.strip()) or "（暂无角色库条目）"
    return f"""# 角色圣经

## 主角

{protagonist or "（暂无主角卡）"}

## 女主/感情线

{heroine or "（暂无或无女主）"}

## 主角组

{team or "（暂无）"}

## 反派

{antagonist or "（暂无反派设计）"}

## 角色库

{library}

## 当前主角状态

```json
{_dump_json(state.get("protagonist_state") or {})}
```

## B路线运行态人物

```json
{_dump_json(state.get("entity_state") or {})}
```
"""


def _render_relationship_map(state: dict[str, Any]) -> str:
    return f"""# 关系图谱

## 运行态关系

```json
{_dump_json(state.get("relationships") or {})}
```

## 说明

如 `index.db` 中已有更细的关系表，webnovel-writer 仍以 `chapter-commit` 后的投影为准；本文件只作为 NCS 写作前的可读关系视图。
"""


def _render_plotlines(project_root: Path, state: dict[str, Any], chapter: int, volume: int) -> str:
    outline = _read_text(project_root / "大纲" / "总纲.md")
    volume_outlines = _read_joined(_outline_files(project_root, volume), empty="（暂无卷详细大纲/章纲）")
    summaries = _read_joined(_latest_files_before_chapter(project_root / ".webnovel" / "summaries", "*.md", chapter, 5, state), empty="（暂无章节摘要）")
    threads = (state.get("plot_threads") or {})
    return f"""# 主要情节线

## 当前进度

- 当前目标章：第{chapter}章
- 当前卷：第{volume}卷

## 全局总纲

{outline or "（暂无总纲）"}

## 当前卷/章纲

{volume_outlines}

## 最近章节摘要

{summaries}

## 运行态情节线

```json
{_dump_json(threads)}
```
"""


def _render_foreshadow(project_root: Path, state: dict[str, Any], chapter_payload: Any, review_payload: Any) -> str:
    memory_dir = project_root / ".webnovel"
    memory_files = [
        memory_dir / "memory_scratchpad.json",
        memory_dir / "project_memory.json",
    ]
    memory_chunks = []
    for path in memory_files:
        value = _read_json(path)
        if value is not None:
            memory_chunks.append(f"## {path.name}\n\n```json\n{_dump_json(value)}\n```")
    return f"""# 伏笔账本

## state.plot_threads.foreshadowing

```json
{_dump_json((state.get("plot_threads") or {}).get("foreshadowing") or [])}
```

## 章节合同相关伏笔/必须节点

```json
{_dump_json(chapter_payload)}
```

## 审查合同禁区与检查点

```json
{_dump_json(review_payload)}
```

## 记忆文件

{chr(10).join(memory_chunks) if memory_chunks else "（暂无）"}
"""


def _render_chapter_roadmap(project_root: Path, chapter: int, volume: int, chapter_payload: Any, review_payload: Any, chapter_outline: str) -> str:
    volume_outlines = _read_joined(_outline_files(project_root, volume), empty="（暂无卷详细大纲/章纲）")
    return f"""# 章节路线图

## 当前目标

- 当前章：第{chapter}章
- 当前卷：第{volume}卷

## 当前章摘录

{chapter_outline or "（暂无当前章摘录；请以章级合同和卷纲为准）"}

## 卷详细大纲/章纲

{volume_outlines}

## 章级合同

```json
{_dump_json(chapter_payload)}
```

## 审查合同

```json
{_dump_json(review_payload)}
```
"""


def _render_dynamic_state(project_root: Path, state: dict[str, Any], chapter: int, volume: int) -> str:
    progress = state.get("progress") or {}
    completed_chapter = progress.get("current_chapter") or state.get("current_chapter") or state.get("last_completed_chapter") or 0
    total_words = progress.get("total_words") or state.get("total_words") or 0
    summaries = _read_joined(_latest_files_before_chapter(project_root / ".webnovel" / "summaries", "*.md", chapter, 5, state), empty="（暂无）")
    state_changes = _read_joined(_latest_files_before_chapter(project_root / ".story-system" / "events", "*.events.json", chapter, 5, state), empty="（暂无）")
    if _route_cutover_invalidates_previous_artifacts(state, chapter):
        index_snapshot = {
            "note": "B路线重写切换中：旧 index.db 投影暂不注入 bridge，避免旧正文事实回流；新第1章提交后重建。",
            "foreshadows": ((state.get("plot_threads") or {}).get("foreshadowing") or []),
        }
    else:
        index_snapshot = _read_index_snapshot(project_root, chapter)
    knowledge_files = _read_knowledge_files(project_root)
    return f"""# 动态状态

## 当前进度

- 卷：第{volume}卷
- 目标章：第{chapter}章
- 已完成章：{completed_chapter}
- 总字数：{total_words}

## 主角当前状态

```json
{_dump_json(state.get("protagonist_state") or {})}
```

## 最近摘要

{summaries}

## 最近事件

{state_changes}

## 资料库快照（index.db）

```json
{_dump_json(index_snapshot)}
```

## knowledge 文件快照

{knowledge_files}
"""


def _render_style_guide(project_root: Path, state: dict[str, Any], master_payload: Any, anti_patterns: Any) -> str:
    style_source = _read_text(project_root / "设定集" / "复合题材-融合逻辑.md")
    if str(state.get("current_stage") or "") == "rewrite_cutover":
        power = "死劫改命系统：通过右眼载体提示当前死劫、命运死劫和结算奖励；不是全知剧透器，不送满级血继。忍道词条只提供本土化能力增益，必须有槽位、反噬、暴露或因果追踪代价；每章必须以动作兑现结果。"
    else:
        power = _read_text(project_root / "设定集" / "力量体系.md")
    return f"""# 风格指南

## 段落模式

web-serial-natural

## Story System 主设定

```json
{_dump_json(master_payload)}
```

## 反模式/毒点

```json
{_dump_json(anti_patterns)}
```

## 题材融合与风格线

{style_source or "（暂无复合题材说明）"}

## 必须保留术语

{power or "（暂无力量体系术语）"}
"""


def _copy_recent_chapters(project_root: Path, bridge_dir: Path, limit: int, target_chapter: int, state: dict[str, Any]) -> None:
    chapters_dir = project_root / "正文"
    target_dir = bridge_dir / "chapters"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    if not chapters_dir.is_dir() or limit <= 0:
        return
    candidates: list[tuple[int, str, Path]] = []
    for path in chapters_dir.glob("*.md"):
        number = _chapter_number_from_path(path)
        if number is None or number >= target_chapter:
            continue
        status = _chapter_status(state, number)
        if "rewrite_pending_old_route_invalid" in status:
            continue
        candidates.append((number, path.name, path))
    for index, (_, _, path) in enumerate(sorted(candidates)[-limit:], start=1):
        safe_name = re.sub(r"^第0*(\d+)章[-_ ]*", r"\1-", path.name)
        if not re.match(r"^\d+", safe_name):
            safe_name = f"ref-{index:02d}-{path.name}"
        shutil.copy2(path, target_dir / safe_name)


def _render_control_card(chapter: int, volume: int, chapter_payload: Any, review_payload: Any, chapter_outline: str) -> str:
    return f"""# 第{chapter}章控制卡

## 章节任务

根据 `07-chapter-roadmap.md`、章级合同和审查合同执行。必须服务当前卷第{volume}卷的主线推进。

## 当前章大纲摘录

{chapter_outline or "（暂无当前章摘录；写作前需要人工确认本章任务）"}

## 本章窄入口

- 优先调用当前章大纲摘录、最近章节、当前技能物品状态。
- 不主动调用中后期计划态内容，除非本章大纲明确埋伏笔。
- 技能和物品只能按当前时间线状态使用，不能提前升级、换手或暴露。
- 若大纲摘录与章级合同冲突，以章级合同和审查合同为准。

## 必须节点

### 章级合同

```json
{_dump_json(chapter_payload)}
```

## 本章禁区

### 审查合同

```json
{_dump_json(review_payload)}
```

## 风格控制

- 段落模式：web-serial-natural
- 目标字数：2000-2500 字，用户/大纲另有要求时优先
- 只改表达不改事实
- 必须保留人物关系、设定边界、时间锚点和伏笔状态

## 输出要求

- 输出到 `chapters/{chapter:02d}-<chapter-title>.md`
- 生成后执行 authenticity pass
- 不得跳过连续性检查
"""


def build_bridge(project_root: Path, *, chapter: int | None, output_dir: Path | None, recent_chapters: int) -> dict[str, Any]:
    state = _read_json(project_root / ".webnovel" / "state.json")
    if not isinstance(state, dict):
        raise FileNotFoundError(f"missing or invalid state.json: {project_root / '.webnovel' / 'state.json'}")

    target_chapter = _chapter_arg(state, chapter)
    volume = _volume_from_outline_headers(project_root, target_chapter) or _volume_for_chapter(state, target_chapter)
    bridge_dir = output_dir or (project_root / ".webnovel" / "tmp" / "ncs-bridge")
    if bridge_dir.exists():
        shutil.rmtree(bridge_dir)
    bridge_dir.mkdir(parents=True, exist_ok=True)
    (bridge_dir / "control-cards").mkdir(parents=True, exist_ok=True)
    (bridge_dir / "logs").mkdir(parents=True, exist_ok=True)

    anti_patterns = _story_json(project_root, "anti")
    previous_artifacts_invalid = _route_cutover_invalidates_previous_artifacts(state, target_chapter)
    master_payload = _story_json(project_root, "master")
    if previous_artifacts_invalid:
        if master_payload is None:
            master_payload = {
                "note": "B路线重写切换中：未找到新版 MASTER_SETTING；以当前总纲、卷纲、state 和章节摘录为准。"
            }
        chapter_payload = None
        review_payload = None
    else:
        chapter_payload = _story_json(project_root, "chapter", chapter=target_chapter)
        review_payload = _story_json(project_root, "review", chapter=target_chapter)
    chapter_outline = _chapter_outline_section(project_root, target_chapter, volume)

    files: dict[str, str] = {
        "00-project-overview.md": _render_project_overview(project_root, state),
        "01-theme-and-proposition.md": _render_theme(state),
        "02-worldbuilding.md": _render_worldbuilding(project_root, state, target_chapter),
        "03-cast-bible.md": _render_cast_bible(project_root, state, target_chapter),
        "04-relationship-map.md": _render_relationship_map(state),
        "05-main-plotlines.md": _render_plotlines(project_root, state, target_chapter, volume),
        "06-foreshadow-ledger.md": _render_foreshadow(project_root, state, chapter_payload, review_payload),
        "07-chapter-roadmap.md": _render_chapter_roadmap(project_root, target_chapter, volume, chapter_payload, review_payload, chapter_outline),
        "08-dynamic-state.md": _render_dynamic_state(project_root, state, target_chapter, volume),
        "09-style-guide.md": _render_style_guide(project_root, state, master_payload, anti_patterns),
    }

    written: list[str] = []
    for filename, content in files.items():
        _write_text(bridge_dir / filename, content)
        written.append(filename)

    control_name = f"{target_chapter:02d}-control-card.md"
    _write_text(bridge_dir / "control-cards" / control_name, _render_control_card(target_chapter, volume, chapter_payload, review_payload, chapter_outline))
    written.append(f"control-cards/{control_name}")
    _copy_recent_chapters(project_root, bridge_dir, recent_chapters, target_chapter, state)

    manifest = {
        "schema_version": 1,
        "project_root": str(project_root),
        "bridge_dir": str(bridge_dir),
        "chapter": target_chapter,
        "volume": volume,
        "standard_files": list(STANDARD_FILES),
        "written": written,
    }
    _write_text(bridge_dir / "bridge-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Novel-Control-Station bridge files from a webnovel-writer project")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    parser.add_argument("--chapter", type=int, default=0, help="目标章节号；默认 current_chapter + 1")
    parser.add_argument("--output-dir", default="", help="输出目录；默认 PROJECT_ROOT/.webnovel/tmp/ncs-bridge")
    parser.add_argument("--recent-chapters", type=int, default=3, help="复制最近 N 章到 NCS chapters/ 作为上下文")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    project_root = resolve_project_root(args.project_root)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    manifest = build_bridge(
        project_root,
        chapter=args.chapter or None,
        output_dir=output_dir,
        recent_chapters=args.recent_chapters,
    )
    if args.format == "json":
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"NCS bridge ready: {manifest['bridge_dir']}")
        print(f"chapter: {manifest['chapter']}")
        print("written:")
        for item in manifest["written"]:
            print(f" - {item}")


if __name__ == "__main__":
    main()
