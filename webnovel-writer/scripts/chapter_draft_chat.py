#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 chat/completions 版正文生成器。

职责：
- 读取正文输入卡 / scene brief / rewrite notes
- 读取 prompts/02_正文生成.md
- 请求本地 OpenAI 兼容 chat/completions 接口
- 回写 `正文/第NNNN章-标题.md`
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

from runtime_compat import enable_windows_utf8_stdio


def _ensure_scripts_path() -> None:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_path()

from chapter_paths import find_chapter_file
from project_locator import resolve_project_root
from security_utils import read_json_safe

try:
    import tomllib  # py311+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _resolve_chapter(project_root: Path, chapter: int) -> int:
    if chapter > 0:
        return chapter
    state = read_json_safe(project_root / ".webnovel" / "state.json", {})
    progress = state.get("progress") or {}
    current = int(progress.get("current_chapter") or state.get("current_chapter") or 0)
    return max(1, current + 1)


def _load_text(path: Path, default: str = "") -> str:
    if not path.is_file():
        return default
    return path.read_text(encoding="utf-8")


def _load_contract_title(project_root: Path, chapter: int) -> str:
    contract = read_json_safe(project_root / ".story-system" / "chapters" / f"chapter_{chapter:03d}_contract.json", {})
    return str(contract.get("title") or f"第{chapter:04d}章").strip()


def _load_local_codex_config(project_root: Path) -> dict[str, Any]:
    local = project_root / ".codex-home" / "config.toml"
    global_ = Path.home() / ".codex" / "config.toml"
    path = local if local.is_file() else global_
    if not path.is_file():
        raise FileNotFoundError(f"未找到 Codex 配置文件：{local} / {global_}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _load_auth_key(project_root: Path) -> str:
    local = project_root / ".codex-home" / "auth.json"
    global_ = Path.home() / ".codex" / "auth.json"
    path = local if local.is_file() else global_
    data = json.loads(path.read_text(encoding="utf-8"))
    key = str(data.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(f"{path} 中缺少 OPENAI_API_KEY")
    return key


def _resolve_chat_endpoint(config: dict[str, Any]) -> tuple[str, str]:
    provider_name = str(config.get("model_provider") or "custom")
    model = str(config.get("model") or "gpt-5.5")
    providers = config.get("model_providers") or {}
    provider = providers.get(provider_name) or providers.get("custom") or {}
    base_url = str(provider.get("base_url") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("Codex 配置里缺少 custom provider base_url")
    if base_url.endswith("/v1"):
        endpoint = f"{base_url}/chat/completions"
    elif "/chat/completions" in base_url:
        endpoint = base_url
    else:
        endpoint = f"{base_url}/v1/chat/completions"
    return endpoint, model


def _build_messages(project_root: Path, chapter: int) -> list[dict[str, str]]:
    tmp = project_root / ".webnovel" / "tmp"
    prompt_text = _load_text(project_root / "prompts" / "02_正文生成.md")
    if not prompt_text:
        prompt_text = _load_text(project_root / "规划" / "No正文生成提示词.md")
    input_card = _load_text(tmp / f"ch{chapter:04d}_input_card.md")
    scene_brief = _load_text(tmp / f"ch{chapter:04d}_scene_brief.md")
    rewrite_notes = _load_text(tmp / f"ch{chapter:04d}_rewrite_notes.md")
    title = _load_contract_title(project_root, chapter)

    user_parts = [
        f"章节标题：{title}",
        "请根据下面材料直接生成正文，不要输出解释，不要输出代码块，不要输出标题行。",
        "输出必须是正文内容本身。",
        "",
        "【正文输入卡】",
        input_card.strip(),
    ]
    if scene_brief.strip():
        user_parts.extend(["", "【scene brief】", scene_brief.strip()])
    if rewrite_notes.strip():
        user_parts.extend(["", "【rewrite notes】", rewrite_notes.strip()])
    user_parts.extend(
        [
            "",
            "最终只返回一个 JSON 对象：",
            '{"body":"正文内容"}',
            "body 里不要再包代码块，不要再写标题。",
        ]
    )
    return [
        {"role": "system", "content": prompt_text.strip()},
        {"role": "user", "content": "\n".join(user_parts).strip()},
    ]


def _extract_body_from_response(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("chat/completions 返回中没有 choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("chat/completions 返回中 message.content 为空")
    content = str(content).strip()
    try:
        parsed = json.loads(content)
        body = str(parsed.get("body") or "").strip()
        if body:
            return body
    except Exception:
        pass
    return content


def _clean_body(body: str) -> str:
    cleaned = body.strip()
    cleaned = re.sub(r"^```(?:text|markdown)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    lines = cleaned.splitlines()
    if lines and re.match(r"^#\s*第\d+章", lines[0].strip()):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def _canonical_flat_path(project_root: Path, chapter: int, title: str) -> Path:
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip()
    if safe_title:
        return project_root / "正文" / f"第{chapter:04d}章-{safe_title}.md"
    return project_root / "正文" / f"第{chapter:04d}章.md"


def _write_manuscript(project_root: Path, chapter: int, title: str, body: str) -> Path:
    chapter_file = _canonical_flat_path(project_root, chapter, title)
    existing = find_chapter_file(project_root, chapter)
    if existing is not None and existing.name == chapter_file.name:
        chapter_file = existing
    chapter_file.parent.mkdir(parents=True, exist_ok=True)
    heading = f"# 第{chapter:04d}章-{title}".strip()
    chapter_file.write_text(f"{heading}\n\n{body.strip()}\n", encoding="utf-8")
    return chapter_file


def generate_chapter(project_root: Path, chapter: int) -> dict[str, Any]:
    chapter = _resolve_chapter(project_root, chapter)
    title = _load_contract_title(project_root, chapter)
    config = _load_local_codex_config(project_root)
    endpoint, model = _resolve_chat_endpoint(config)
    api_key = _load_auth_key(project_root)
    messages = _build_messages(project_root, chapter)
    body = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    manuscript_body = _clean_body(_extract_body_from_response(payload))
    chapter_path = _write_manuscript(project_root, chapter, title, manuscript_body)
    return {
        "chapter": chapter,
        "title": title,
        "chapter_file": str(chapter_path),
        "endpoint": endpoint,
        "model": model,
        "chars": len(manuscript_body),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="本地 chat/completions 版正文生成器")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    parser.add_argument("--chapter", type=int, default=0, help="目标章节号；默认 current_chapter + 1")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    project_root = resolve_project_root(args.project_root)
    payload = generate_chapter(project_root, args.chapter)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"chapter: {payload['chapter']}")
        print(f"title: {payload['title']}")
        print(f"chapter_file: {payload['chapter_file']}")
        print(f"endpoint: {payload['endpoint']}")
        print(f"model: {payload['model']}")
        print(f"chars: {payload['chars']}")


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
