#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chapter_outline_loader import load_chapter_outline
from chapter_paths import extract_chapter_title, find_chapter_file

from .config import DataModulesConfig
from .index_manager import (
    ChapterMeta,
    ChapterReadingPowerMeta,
    IndexManager,
    RelationshipEventMeta,
    ReviewMetrics,
    StateChangeMeta,
)


class IndexProjectionWriter:
    ENTITY_TYPE_MAP = {
        "角色": "角色",
        "人物": "角色",
        "群体": "角色",
        "地点": "地点",
        "场景": "地点",
        "物品": "物品",
        "道具": "物品",
        "能力": "招式",
        "技能": "招式",
        "招式": "招式",
        "势力": "势力",
    }

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def apply(self, commit_payload: dict) -> dict:
        if commit_payload["meta"]["status"] != "accepted":
            return {"applied": False, "writer": "index", "reason": "commit_rejected"}

        manager = IndexManager(DataModulesConfig.from_project_root(self.project_root))
        applied_count = 0

        for delta in self._collect_entity_deltas(commit_payload):
            result = manager.apply_entity_delta(delta)
            if result:
                applied_count += 1
            entity_type = str(delta.get("type") or "").strip()
            entity_id = str(delta.get("entity_id") or delta.get("id") or "").strip()
            for alias in delta.get("aliases") or []:
                alias_text = str(alias or "").strip()
                if alias_text and entity_id and entity_type:
                    if manager.register_alias(alias_text, entity_id, entity_type):
                        applied_count += 1
            for relation in delta.get("relationships") or []:
                if manager.apply_entity_delta(relation):
                    applied_count += 1
                event = self._build_relationship_event(relation)
                if event and manager.record_relationship_event(event):
                    applied_count += 1

        for change in self._collect_state_changes(commit_payload):
            if manager.record_state_change(change):
                applied_count += 1

        for event in self._collect_relationship_events(commit_payload):
            if manager.record_relationship_event(event):
                applied_count += 1

        chapter_meta = self._build_chapter_meta(commit_payload)
        if chapter_meta is not None:
            manager.add_chapter(chapter_meta)
            applied_count += 1

        reading_power = self._build_reading_power_meta(commit_payload)
        if reading_power is not None:
            manager.save_chapter_reading_power(reading_power)
            applied_count += 1

        review_metrics = self._build_review_metrics(commit_payload)
        if review_metrics is not None:
            manager.save_review_metrics(review_metrics)
            applied_count += 1

        return {
            "applied": applied_count > 0,
            "writer": "index",
            "applied_count": applied_count,
        }

    def _normalize_entity_type(self, raw_type: Any) -> str:
        value = str(raw_type or "角色").strip()
        return self.ENTITY_TYPE_MAP.get(value, value or "角色")

    def _collect_entity_deltas(self, commit_payload: dict) -> list[dict]:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        deltas: list[dict] = []

        for delta in commit_payload.get("entity_deltas") or []:
            if not isinstance(delta, dict):
                continue
            payload = dict(delta.get("payload") or {})
            entity_id = str(delta.get("entity_id") or delta.get("id") or payload.get("id") or "").strip()
            if not entity_id:
                continue
            canonical_name = str(
                delta.get("canonical_name")
                or delta.get("name")
                or payload.get("name")
                or entity_id
            ).strip()
            entity_type = self._normalize_entity_type(delta.get("type") or payload.get("type") or "角色")
            flattened = {
                "entity_id": entity_id,
                "canonical_name": canonical_name,
                "type": entity_type,
                "tier": str(delta.get("tier") or payload.get("tier") or "装饰").strip() or "装饰",
                "current": dict(delta.get("current") or payload.get("attributes") or {}),
                "desc": str(delta.get("desc") or payload.get("description") or "").strip(),
                "chapter": int(delta.get("chapter") or payload.get("first_appearance") or chapter or 0),
                "first_appearance": int(payload.get("first_appearance") or delta.get("first_appearance") or chapter or 0),
                "aliases": [str(x).strip() for x in (payload.get("aliases") or delta.get("aliases") or []) if str(x).strip()],
                "relationships": self._flatten_payload_relationships(entity_id, payload.get("relationships") or [], chapter),
                "is_protagonist": str(payload.get("tier") or "") == "主角" or bool(delta.get("is_protagonist")),
            }
            deltas.append(flattened)

        for event in commit_payload.get("accepted_events") or []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = dict(event.get("payload") or {})
            event_chapter = int(event.get("chapter") or chapter or 0)
            if event_type == "relationship_changed":
                from_entity = str(payload.get("from_entity") or event.get("subject") or "").strip()
                to_entity = str(payload.get("to_entity") or payload.get("to") or "").strip()
                rel_type = str(
                    payload.get("relationship_type")
                    or payload.get("relation_type")
                    or payload.get("type")
                    or ""
                ).strip()
                if from_entity and to_entity and rel_type:
                    deltas.append(
                        {
                            "from_entity": from_entity,
                            "to_entity": to_entity,
                            "relationship_type": rel_type,
                            "description": str(payload.get("description") or event.get("description") or "").strip(),
                            "chapter": event_chapter,
                        }
                    )
            elif event_type == "artifact_obtained":
                entity_id = str(
                    payload.get("artifact_id")
                    or payload.get("entity_id")
                    or payload.get("id")
                    or event.get("subject")
                    or ""
                ).strip()
                if not entity_id:
                    continue
                current = {}
                owner = str(payload.get("owner") or payload.get("holder") or "").strip()
                location = str(payload.get("location") or "").strip()
                if owner:
                    current["holder"] = owner
                if location:
                    current["location"] = location
                deltas.append(
                    {
                        "entity_id": entity_id,
                        "canonical_name": str(payload.get("name") or event.get("subject") or entity_id).strip(),
                        "type": self._normalize_entity_type(payload.get("type") or "物品"),
                        "current": current,
                        "desc": str(payload.get("description") or event.get("description") or "").strip(),
                        "chapter": event_chapter,
                    }
                )
        return deltas

    def _flatten_payload_relationships(self, source_entity: str, relationships: list[Any], chapter: int) -> list[dict]:
        flattened: list[dict] = []
        for row in relationships:
            if not isinstance(row, dict):
                continue
            target = str(row.get("target") or row.get("to_entity") or row.get("to") or "").strip()
            relation = str(row.get("relation") or row.get("relationship_type") or row.get("type") or "").strip()
            if not target or not relation:
                continue
            flattened.append(
                {
                    "from_entity": source_entity,
                    "to_entity": target,
                    "relationship_type": relation,
                    "description": str(row.get("description") or "").strip(),
                    "chapter": int(row.get("chapter") or chapter or 0),
                }
            )
        return flattened

    def _collect_state_changes(self, commit_payload: dict) -> list[StateChangeMeta]:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        changes: list[StateChangeMeta] = []
        seen: set[tuple[str, str, int, str]] = set()
        for delta in commit_payload.get("state_deltas") or []:
            if not isinstance(delta, dict):
                continue
            entity_id = str(delta.get("entity_id") or "").strip()
            field = str(delta.get("field") or "").strip()
            if not entity_id or not field:
                continue
            new_value = delta.get("new") if "new" in delta else delta.get("new_value")
            old_value = delta.get("old") if "old" in delta else delta.get("old_value")
            key = (entity_id, field, chapter, str(new_value))
            if key in seen:
                continue
            seen.add(key)
            changes.append(
                StateChangeMeta(
                    entity_id=entity_id,
                    field=field,
                    old_value="" if old_value is None else str(old_value),
                    new_value="" if new_value is None else str(new_value),
                    reason="chapter_commit",
                    chapter=chapter,
                )
            )
        return changes

    def _collect_relationship_events(self, commit_payload: dict) -> list[RelationshipEventMeta]:
        events: list[RelationshipEventMeta] = []
        for event in commit_payload.get("accepted_events") or []:
            if not isinstance(event, dict):
                continue
            built = self._build_relationship_event(event)
            if built is not None:
                events.append(built)
        return events

    def _build_relationship_event(self, source: dict) -> RelationshipEventMeta | None:
        payload = dict(source.get("payload") or {})
        from_entity = str(source.get("from_entity") or payload.get("from_entity") or source.get("subject") or "").strip()
        to_entity = str(source.get("to_entity") or payload.get("to_entity") or payload.get("to") or "").strip()
        rel_type = str(
            source.get("relationship_type")
            or payload.get("relationship_type")
            or payload.get("relation_type")
            or source.get("type")
            or payload.get("type")
            or ""
        ).strip()
        chapter = int(source.get("chapter") or 0)
        if not from_entity or not to_entity or not rel_type or chapter <= 0:
            return None
        return RelationshipEventMeta(
            from_entity=from_entity,
            to_entity=to_entity,
            type=rel_type,
            chapter=chapter,
            action=str(payload.get("action") or source.get("action") or "update").strip() or "update",
            description=str(payload.get("description") or source.get("description") or "").strip(),
            evidence=str(payload.get("evidence") or "").strip(),
            confidence=float(payload.get("confidence") or source.get("confidence") or 1.0),
            strength=float(payload.get("strength") or 0.5),
        )

    def _build_chapter_meta(self, commit_payload: dict) -> ChapterMeta | None:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        if chapter <= 0:
            return None
        chapter_file = find_chapter_file(self.project_root, chapter)
        summary_text = str(commit_payload.get("summary_text") or "")
        summary = self._extract_summary_body(summary_text)
        location = self._extract_summary_frontmatter_list(summary_text, "location")
        if isinstance(location, list):
            location = "、".join(location)
        location = str(location or self._first_event_location(commit_payload) or "").strip()
        title = extract_chapter_title(self.project_root, chapter)
        if not title:
            outline_text = load_chapter_outline(self.project_root, chapter, max_chars=None)
            title = self._extract_outline_title(outline_text, chapter)
        word_count = 0
        if chapter_file and chapter_file.is_file():
            word_count = self._count_chapter_words(chapter_file.read_text(encoding="utf-8"))
        characters = self._collect_chapter_characters(commit_payload)
        return ChapterMeta(
            chapter=chapter,
            title=title,
            location=location,
            word_count=word_count,
            characters=characters,
            summary=summary,
        )

    def _build_reading_power_meta(self, commit_payload: dict) -> ChapterReadingPowerMeta | None:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        if chapter <= 0:
            return None
        summary_text = str(commit_payload.get("summary_text") or "")
        hook_type = self._extract_summary_frontmatter_value(summary_text, "hook_type")
        hook_strength = self._extract_summary_frontmatter_value(summary_text, "hook_strength") or "medium"
        return ChapterReadingPowerMeta(
            chapter=chapter,
            hook_type=str(hook_type or "").strip(),
            hook_strength=str(hook_strength or "medium").strip() or "medium",
            coolpoint_patterns=[],
            micropayoffs=[],
            hard_violations=[],
            soft_suggestions=[],
            is_transition=False,
            override_count=0,
            debt_balance=0.0,
        )

    def _build_review_metrics(self, commit_payload: dict) -> ReviewMetrics | None:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        review_result = dict(commit_payload.get("review_result") or {})
        if chapter <= 0 or not review_result:
            return None
        overall_score = review_result.get("review_score") or review_result.get("overall_score") or 0
        dimension_scores = {}
        for key, value in (review_result.get("审查维度") or {}).items():
            if isinstance(value, dict) and "score" in value:
                try:
                    dimension_scores[str(key)] = float(value.get("score") or 0)
                except (TypeError, ValueError):
                    continue
        severity_counts: dict[str, int] = {}
        critical_issues: list[str] = []
        for issue in review_result.get("问题清单") or []:
            if not isinstance(issue, dict):
                continue
            severity = str(issue.get("severity") or "unknown").strip() or "unknown"
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            problem = str(issue.get("问题") or issue.get("description") or "").strip()
            if problem:
                critical_issues.append(problem)
        return ReviewMetrics(
            start_chapter=chapter,
            end_chapter=chapter,
            overall_score=float(overall_score or 0),
            dimension_scores=dimension_scores,
            severity_counts=severity_counts,
            critical_issues=critical_issues,
            notes=str(review_result.get("总结") or "").strip(),
        )

    def _collect_chapter_characters(self, commit_payload: dict) -> list[str]:
        characters: list[str] = []
        seen: set[str] = set()
        for delta in self._collect_entity_deltas(commit_payload):
            entity_id = str(delta.get("entity_id") or "").strip()
            entity_type = str(delta.get("type") or "").strip()
            if entity_id and entity_type == "角色" and entity_id not in seen:
                seen.add(entity_id)
                characters.append(entity_id)
        for event in commit_payload.get("accepted_events") or []:
            if not isinstance(event, dict):
                continue
            for participant in event.get("participants") or []:
                entity_id = str(participant or "").strip()
                if entity_id and entity_id not in seen:
                    seen.add(entity_id)
                    characters.append(entity_id)
        return characters

    def _first_event_location(self, commit_payload: dict) -> str:
        for event in commit_payload.get("accepted_events") or []:
            if not isinstance(event, dict):
                continue
            location = str(event.get("location") or "").strip()
            if location:
                return location
        return ""

    def _extract_summary_body(self, summary_text: str) -> str:
        marker = "## 剧情摘要"
        if marker not in summary_text:
            return summary_text.strip()
        body = summary_text.split(marker, 1)[1]
        for next_marker in ("## 伏笔", "## 承接点"):
            if next_marker in body:
                body = body.split(next_marker, 1)[0]
        return body.strip()

    def _extract_summary_frontmatter_value(self, summary_text: str, key: str) -> str:
        if not summary_text.startswith("---"):
            return ""
        parts = summary_text.split("---", 2)
        if len(parts) < 3:
            return ""
        frontmatter = parts[1]
        prefix = f"{key}:"
        for line in frontmatter.splitlines():
            stripped = line.strip()
            if stripped.startswith(prefix):
                return stripped[len(prefix):].strip().strip('"')
        return ""

    def _extract_summary_frontmatter_list(self, summary_text: str, key: str) -> Any:
        value = self._extract_summary_frontmatter_value(summary_text, key)
        if value.startswith("[") and value.endswith("]"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    def _extract_outline_title(self, outline_text: str, chapter: int) -> str:
        import re
        match = re.search(rf"^#+\s*第\s*{chapter}\s*章[：:](.+)$", outline_text, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _count_chapter_words(self, content: str) -> int:
        import re
        text = re.sub(r'```[\s\S]*?```', '', content)
        text = re.sub(r'#+ .+', '', text)
        text = re.sub(r'---', '', text)
        return len(text.strip())
