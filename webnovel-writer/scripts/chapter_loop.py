#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节自动循环执行器。

目标：
- 按“四段流程”驱动章节生产：
  1) input_card
  2) draft
  3) review
  4) gate
- 若被打回，读取 rewrite_notes 再次调用重生命令
- 直到 pass、达到最大轮数、或检测到风格卡死

说明：
- 本脚本不内置大模型正文生成能力
- 需要通过配置提供各阶段命令模板
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from runtime_compat import enable_windows_utf8_stdio


def _ensure_scripts_path() -> None:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_path()

from chapter_gate import run_gate
from project_locator import resolve_project_root
from security_utils import atomic_write_json, read_json_safe


LOOP_CONFIG_REL = Path(".webnovel") / "chapter_loop_config.json"


def _load_state(project_root: Path) -> dict[str, Any]:
    return read_json_safe(project_root / ".webnovel" / "state.json", {})


def _resolve_chapter(project_root: Path, chapter: int) -> int:
    if chapter > 0:
        return chapter
    state = _load_state(project_root)
    progress = state.get("progress") or {}
    current = int(progress.get("current_chapter") or state.get("current_chapter") or 0)
    return max(1, current + 1)


def _load_loop_config(project_root: Path) -> dict[str, Any]:
    config = read_json_safe(project_root / LOOP_CONFIG_REL, {})
    if not isinstance(config, dict):
        return {}
    return config


def _read_text_if_exists(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _signature(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _build_context(project_root: Path, chapter: int) -> dict[str, str]:
    tmp = project_root / ".webnovel" / "tmp"
    bridge_dir = tmp / "ncs-bridge"
    return {
        "project_root": str(project_root),
        "chapter": str(chapter),
        "chapter_num": str(chapter),
        "chapter_padded": f"{chapter:04d}",
        "tmp_dir": str(tmp),
        "bridge_dir": str(bridge_dir),
        "prewrite_file": str(tmp / f"ch{chapter:04d}_prewrite.md"),
        "input_card_file": str(tmp / f"ch{chapter:04d}_input_card.md"),
        "scene_brief_file": str(tmp / f"ch{chapter:04d}_scene_brief.md"),
        "rewrite_notes_file": str(tmp / f"ch{chapter:04d}_rewrite_notes.md"),
        "gate_result_file": str(tmp / f"ch{chapter:04d}_gate_result.json"),
        "anti_ai_scan_file": str(tmp / f"ch{chapter:04d}_anti_ai_scan.md"),
        "loop_result_file": str(tmp / f"ch{chapter:04d}_loop_result.json"),
    }


def _invoke_stage(project_root: Path, chapter: int, cmd_template: str, stage_name: str) -> dict[str, Any]:
    context = _build_context(project_root, chapter)
    cmd = cmd_template.format(**context)
    proc = subprocess.run(
        cmd,
        shell=True,
        executable="/bin/zsh",
        cwd=str(project_root),
        text=True,
        capture_output=True,
    )
    return {
        "stage": stage_name,
        "command": cmd,
        "returncode": int(proc.returncode or 0),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def _write_loop_result(project_root: Path, chapter: int, payload: dict[str, Any]) -> Path:
    out = project_root / ".webnovel" / "tmp" / f"ch{chapter:04d}_loop_result.json"
    atomic_write_json(out, payload, backup=False)
    return out


def _resolve_stage_templates(
    config: dict[str, Any],
    generator_cmd_override: str,
) -> dict[str, str]:
    draft_cmd = str(
        generator_cmd_override
        or config.get("draft_cmd_template")
        or config.get("generator_cmd_template")
        or os.environ.get("WEBNOVEL_DRAFT_CMD")
        or os.environ.get("WEBNOVEL_GENERATOR_CMD")
        or ""
    ).strip()
    return {
        "input_card": str(config.get("input_card_cmd_template") or os.environ.get("WEBNOVEL_INPUT_CARD_CMD") or "").strip(),
        "draft": draft_cmd,
        "rewrite": str(config.get("rewrite_cmd_template") or os.environ.get("WEBNOVEL_REWRITE_CMD") or "").strip(),
        "review": str(config.get("review_cmd_template") or os.environ.get("WEBNOVEL_REVIEW_CMD") or "").strip(),
    }


def _stage_exists(project_root: Path, chapter: int, name: str) -> bool:
    ctx = _build_context(project_root, chapter)
    mapping = {
        "input_card": Path(ctx["input_card_file"]),
        "gate_result": Path(ctx["gate_result_file"]),
        "anti_ai_scan": Path(ctx["anti_ai_scan_file"]),
        "rewrite_notes": Path(ctx["rewrite_notes_file"]),
    }
    target = mapping.get(name)
    return bool(target and target.is_file())


def _build_not_configured_result(chapter: int, missing_stage: str, project_root: Path) -> dict[str, Any]:
    return {
        "chapter": chapter,
        "status": "generator_not_configured",
        "message": f"未配置 {missing_stage} 阶段命令，无法自动执行完整章节循环。",
        "missing_stage": missing_stage,
        "config_path": str(project_root / LOOP_CONFIG_REL),
        "env_vars": {
            "input_card": "WEBNOVEL_INPUT_CARD_CMD",
            "draft": "WEBNOVEL_DRAFT_CMD / WEBNOVEL_GENERATOR_CMD",
            "rewrite": "WEBNOVEL_REWRITE_CMD",
            "review": "WEBNOVEL_REVIEW_CMD",
        },
        "next_action": "configure_generator",
    }


def run_loop(
    project_root: Path,
    chapter: int,
    max_rounds: int,
    stop_on_same_reason_twice: bool,
    generator_cmd_override: str = "",
) -> dict[str, Any]:
    chapter = _resolve_chapter(project_root, chapter)
    config = _load_loop_config(project_root)
    templates = _resolve_stage_templates(config, generator_cmd_override)

    if not templates["draft"]:
        return _build_not_configured_result(chapter, "draft", project_root)

    rounds: list[dict[str, Any]] = []
    last_signature: tuple[str, ...] | None = None
    repeated_same_reason_count = 0
    input_card_stage: Optional[dict[str, Any]] = None

    if templates["input_card"]:
        input_card_stage = _invoke_stage(project_root, chapter, templates["input_card"], "input_card")
        if input_card_stage["returncode"] != 0:
            result = {
                "chapter": chapter,
                "status": "input_card_failed",
                "input_card_stage": input_card_stage,
                "next_action": "fix_input_card_command",
            }
            _write_loop_result(project_root, chapter, result)
            return result
    elif not _stage_exists(project_root, chapter, "input_card"):
        return _build_not_configured_result(chapter, "input_card", project_root)
    else:
        input_card_stage = {
            "stage": "input_card",
            "command": "",
            "returncode": 0,
            "stdout": "reused existing input card",
            "stderr": "",
        }

    for round_no in range(1, max_rounds + 1):
        active_draft_template = templates["draft"] if round_no == 1 or not templates["rewrite"] else templates["rewrite"]
        draft = _invoke_stage(project_root, chapter, active_draft_template, "draft" if round_no == 1 or not templates["rewrite"] else "rewrite")

        if draft["returncode"] != 0:
            result = {
                "chapter": chapter,
                "status": "generator_failed",
                "input_card_stage": input_card_stage,
                "final_round": round_no,
                "rounds": rounds + [{
                    "round": round_no,
                    "draft": {
                        "returncode": draft["returncode"],
                        "command": draft["command"],
                        "stdout_tail": draft["stdout"],
                        "stderr_tail": draft["stderr"],
                    },
                }],
                "next_action": "fix_generator_command",
            }
            _write_loop_result(project_root, chapter, result)
            return result

        review_stage: Optional[dict[str, Any]] = None
        if templates["review"]:
            review_stage = _invoke_stage(project_root, chapter, templates["review"], "review")
            if review_stage["returncode"] != 0:
                result = {
                    "chapter": chapter,
                    "status": "review_failed",
                    "input_card_stage": input_card_stage,
                    "final_round": round_no,
                    "rounds": rounds + [{
                        "round": round_no,
                        "draft": {
                            "returncode": draft["returncode"],
                            "command": draft["command"],
                            "stdout_tail": draft["stdout"],
                            "stderr_tail": draft["stderr"],
                        },
                        "review": {
                            "returncode": review_stage["returncode"],
                            "command": review_stage["command"],
                            "stdout_tail": review_stage["stdout"],
                            "stderr_tail": review_stage["stderr"],
                        },
                    }],
                    "next_action": "fix_review_command",
                }
                _write_loop_result(project_root, chapter, result)
                return result

        gate = run_gate(project_root, chapter)

        round_payload = {
            "round": round_no,
            "draft": {
                "returncode": draft["returncode"],
                "command": draft["command"],
                "stdout_tail": draft["stdout"],
                "stderr_tail": draft["stderr"],
            },
            "gate": {
                "status": gate["status"],
                "ai_style_score": gate["ai_style_score"],
                "rewrite_reasons": gate["rewrite_reasons"],
                "next_action": gate["next_action"],
            },
        }
        if review_stage is not None:
            round_payload["review"] = {
                "returncode": review_stage["returncode"],
                "command": review_stage["command"],
                "stdout_tail": review_stage["stdout"],
                "stderr_tail": review_stage["stderr"],
            }
        rounds.append(round_payload)

        if gate["status"] == "pass":
            result = {
                "chapter": chapter,
                "status": "pass",
                "input_card_stage": input_card_stage,
                "final_round": round_no,
                "rounds": rounds,
                "next_action": "commit",
            }
            _write_loop_result(project_root, chapter, result)
            return result

        current_signature = _signature(gate.get("rewrite_reasons") or [])
        if current_signature and current_signature == last_signature:
            repeated_same_reason_count += 1
        else:
            repeated_same_reason_count = 0
        last_signature = current_signature

        if stop_on_same_reason_twice and repeated_same_reason_count >= 1:
            result = {
                "chapter": chapter,
                "status": "generator_style_stuck",
                "input_card_stage": input_card_stage,
                "final_round": round_no,
                "rounds": rounds,
                "next_action": "change_style_anchor_or_prompt",
                "stuck_signature": list(current_signature),
            }
            _write_loop_result(project_root, chapter, result)
            return result

    result = {
        "chapter": chapter,
        "status": "max_rounds_reached",
        "input_card_stage": input_card_stage,
        "final_round": max_rounds,
        "rounds": rounds,
        "next_action": "manual_intervention",
    }
    _write_loop_result(project_root, chapter, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="章节自动循环执行器")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    parser.add_argument("--chapter", type=int, default=0, help="目标章节号；默认 current_chapter + 1")
    parser.add_argument("--max-rounds", type=int, default=3, help="最大自动重生轮数")
    parser.add_argument("--no-stop-on-same-reason", action="store_true", help="同因二次失败时不要提前停机")
    parser.add_argument("--generator-cmd", default="", help="覆盖 draft_cmd_template / generator_cmd_template")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    project_root = resolve_project_root(args.project_root)
    payload = run_loop(
        project_root=project_root,
        chapter=args.chapter,
        max_rounds=args.max_rounds,
        stop_on_same_reason_twice=not args.no_stop_on_same_reason,
        generator_cmd_override=args.generator_cmd,
    )

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"chapter: {payload.get('chapter')}")
        print(f"status: {payload.get('status')}")
        print(f"next_action: {payload.get('next_action')}")
        if payload.get("status") == "generator_not_configured":
            print(f"config_path: {payload.get('config_path')}")
            print(f"env_var: {payload.get('env_var')}")
        if "final_round" in payload:
            print(f"final_round: {payload.get('final_round')}")


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
