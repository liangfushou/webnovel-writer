#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import re

from chapter_paths import find_chapter_file

from .state_validator import normalize_foreshadowing_list, normalize_state_runtime_sections
from .story_contracts import read_json_if_exists, write_json


class StateProjectionWriter:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def apply(self, commit_payload: dict) -> dict:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        status = commit_payload["meta"]["status"]

        if status == "rejected":
            if chapter > 0:
                state_path = self.project_root / ".webnovel" / "state.json"
                state = read_json_if_exists(state_path) or {}
                progress = state.setdefault("progress", {})
                chapter_status = progress.setdefault("chapter_status", {})
                chapter_status[str(chapter)] = "chapter_rejected"
                write_json(state_path, state)
            return {"applied": True, "writer": "state", "reason": "commit_rejected_status_updated"}

        if status != "accepted":
            return {"applied": False, "writer": "state", "reason": f"unknown_status:{status}"}

        state_path = self.project_root / ".webnovel" / "state.json"
        state = read_json_if_exists(state_path) or {}
        entity_state = state.setdefault("entity_state", {})
        progress = state.setdefault("progress", {})
        chapter_status = progress.setdefault("chapter_status", {})
        plot_threads = state.setdefault("plot_threads", {})

        applied_count = 0
        for delta in self._collect_state_deltas(commit_payload):
            entity_id = str(delta.get("entity_id") or "").strip()
            field = str(delta.get("field") or "").strip()
            if not entity_id or not field:
                continue
            entity_state.setdefault(entity_id, {})[field] = delta.get("new")
            applied_count += 1

        if chapter > 0:
            chapter_status[str(chapter)] = "chapter_committed"
            progress["current_chapter"] = max(int(progress.get("current_chapter") or 0), chapter)
            progress["total_words"] = self._calculate_total_words(chapter_status)
            # Keep legacy top-level progress fields in sync for older menus/panels.
            state["current_chapter"] = max(int(state.get("current_chapter") or 0), chapter)
            state["last_completed_chapter"] = max(int(state.get("last_completed_chapter") or 0), chapter)

        merged_foreshadowing = self._merge_foreshadowing(
            plot_threads.get("foreshadowing") or [],
            self._collect_foreshadowing_items(commit_payload),
        )
        plot_threads["foreshadowing"] = normalize_foreshadowing_list(merged_foreshadowing)
        normalize_state_runtime_sections(state)

        write_json(state_path, state)
        return {
            "applied": applied_count > 0 or chapter > 0 or bool(merged_foreshadowing),
            "writer": "state",
            "applied_count": applied_count,
        }

    def _merge_foreshadowing(self, existing_items: list[dict], new_items: list[dict]) -> list[dict]:
        merged: list[dict] = []
        seen: dict[str, int] = {}
        for item in list(existing_items) + list(new_items):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("description") or "").strip()
            if not content:
                continue
            normalized = dict(item)
            normalized["content"] = content
            key = content
            if key in seen:
                merged[seen[key]] = {**merged[seen[key]], **normalized}
            else:
                seen[key] = len(merged)
                merged.append(normalized)
        return merged

    def _collect_foreshadowing_items(self, commit_payload: dict) -> list[dict]:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        items: list[dict] = []
        for event in commit_payload.get("accepted_events") or []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = dict(event.get("payload") or {})
            content = str(payload.get("content") or payload.get("description") or event.get("description") or "").strip()
            if event_type in {"open_loop_created", "promise_created"} and content:
                items.append(
                    {
                        "content": content,
                        "status": "未回收",
                        "planted_chapter": int(event.get("chapter") or chapter or 0),
                        "target_chapter": int(payload.get("target_chapter") or 0) or None,
                        "tier": str(payload.get("tier") or "支线").strip() or "支线",
                    }
                )
            elif event_type in {"open_loop_closed", "promise_paid_off"} and content:
                items.append(
                    {
                        "content": content,
                        "status": "已回收",
                        "resolved_chapter": int(event.get("chapter") or chapter or 0),
                        "tier": str(payload.get("tier") or "支线").strip() or "支线",
                    }
                )

        summary_text = str(commit_payload.get("summary_text") or "")
        items.extend(self._extract_foreshadowing_from_summary(summary_text, chapter))
        return items

    def _extract_foreshadowing_from_summary(self, summary_text: str, chapter: int) -> list[dict]:
        marker = "## 伏笔"
        if marker not in summary_text:
            return []
        body = summary_text.split(marker, 1)[1]
        if "## 承接点" in body:
            body = body.split("## 承接点", 1)[0]
        items: list[dict] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith("-"):
                continue
            content = stripped.lstrip("-").strip()
            content = re.sub(r"^\[[^\]]+\]\s*", "", content).strip()
            if not content:
                continue
            items.append(
                {
                    "content": content,
                    "status": "未回收",
                    "planted_chapter": chapter,
                    "target_chapter": chapter + 100 if chapter > 0 else None,
                    "tier": "支线",
                }
            )
        return items

    def _calculate_total_words(self, chapter_status: dict) -> int:
        total_words = 0
        for chapter_text, status in chapter_status.items():
            if status != "chapter_committed":
                continue
            try:
                chapter_num = int(chapter_text)
            except (TypeError, ValueError):
                continue
            chapter_file = find_chapter_file(self.project_root, chapter_num)
            if not chapter_file or not chapter_file.is_file():
                continue
            total_words += self._count_chapter_words(chapter_file.read_text(encoding="utf-8"))
        return total_words

    @staticmethod
    def _count_chapter_words(content: str) -> int:
        text = re.sub(r'```[\s\S]*?```', '', content)
        text = re.sub(r'#+ .+', '', text)
        text = re.sub(r'---', '', text)
        return len(text.strip())

    def _collect_state_deltas(self, commit_payload: dict) -> list[dict]:
        deltas = [dict(delta) for delta in (commit_payload.get("state_deltas") or []) if isinstance(delta, dict)]
        seen = {
            (
                str(delta.get("entity_id") or "").strip(),
                str(delta.get("field") or "").strip(),
            )
            for delta in deltas
        }

        for event in commit_payload.get("accepted_events") or []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = dict(event.get("payload") or {})
            entity_id = str(payload.get("entity_id") or event.get("subject") or "").strip()
            if not entity_id:
                continue

            field = ""
            if event_type == "power_breakthrough":
                field = str(payload.get("field") or "realm").strip()
            elif event_type == "character_state_changed":
                field = str(payload.get("field") or "").strip()
            else:
                continue

            key = (entity_id, field)
            if not field or key in seen:
                continue

            seen.add(key)
            deltas.append(
                {
                    "entity_id": entity_id,
                    "field": field,
                    "old": payload.get("old") if "old" in payload else payload.get("from"),
                    "new": payload.get("new") if "new" in payload else payload.get("to"),
                }
            )
        return deltas
