#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用章节 gate-runner。

功能：
- 读取任意章节正文
- 按 .webnovel/anti_ai_checklist.md 的核心规则做高频次扫描
- 输出：
  - .webnovel/tmp/chNNNN_anti_ai_scan.md
  - .webnovel/tmp/chNNNN_gate_result.json
  - .webnovel/tmp/chNNNN_rewrite_notes.md（仅打回时）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
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
from security_utils import atomic_write_json, read_json_safe


WEAK_ADVERBS = ["微微", "轻轻", "缓缓", "淡淡"]
JUDGEMENT_PATTERNS = [
    "他终于明白",
    "他这才意识到",
    "原来",
    "这一刻",
    "他知道",
    "果然",
    "不是梦，也不是",
    "意思就是",
]
TEMPLATE_ACTIONS = [
    "深吸一口气",
    "眼神一凛",
    "瞳孔一缩",
    "嘴角一勾",
    "心里一沉",
    "后背一凉",
]
PROMO_WORDS = [
    "标志着",
    "象征着",
    "彰显",
    "至关重要",
    "关键性",
    "重要时刻",
    "格局",
    "见证了",
    "不断演变",
]
VAGUE_ATTRS = [
    "专家认为",
    "有人指出",
    "观察者认为",
    "行业报告显示",
    "一些人觉得",
    "多个来源",
]
LEVEL1_BANNED = [
    "仿佛",
    "宛若",
    "犹如",
    "一丝",
    "一抹",
    "不禁",
    "微微",
    "轻轻",
    "缓缓",
    "淡淡",
    "眼中闪过",
    "嘴角勾起",
    "眉头微皱",
    "心中一动",
    "心头一震",
    "心中暗道",
]
CHAT_TRACES = [
    "当然",
    "希望这对你有帮助",
    "请告诉我",
    "这是一个",
]
DISCLAIMERS = [
    "截至",
    "根据我最后的训练",
    "基于现有资料",
    "虽然资料有限",
    "根据可用信息",
]
ENDING_SUMMARIES = [
    "他终于明白",
    "这一刻",
    "他知道",
    "更大的风暴即将来临",
]
EXPLANATION_CUES = [
    "意思就是",
    "也就是说",
    "这说明",
    "这意味着",
    "原来",
    "他懂了",
    "他明白",
    "他知道",
]
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _load_state(project_root: Path) -> dict[str, Any]:
    return read_json_safe(project_root / ".webnovel" / "state.json", {})


def _resolve_chapter(project_root: Path, chapter: int) -> int:
    if chapter > 0:
        return chapter
    state = _load_state(project_root)
    progress = state.get("progress") or {}
    current = int(progress.get("current_chapter") or state.get("current_chapter") or 0)
    return max(1, current + 1)


def _read_manuscript(path: Path) -> tuple[str, str, list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    body_lines = lines[:]
    if body_lines and re.match(r"^#\s*第\d+章", body_lines[0].strip()):
        body_lines = body_lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
    body = "\n".join(body_lines).strip()
    return text, body, lines


def _split_paragraphs(body: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?]+", text) if s.strip()]


def _count_occurrences(text: str, patterns: list[str]) -> dict[str, int]:
    return {pattern: text.count(pattern) for pattern in patterns if text.count(pattern) > 0}


def _detect_markdown_pollution(lines: list[str]) -> list[str]:
    hits: list[str] = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        # 允许第一行章节标题
        if idx == 1 and re.match(r"^#\s*第\d+章", line):
            continue
        if "**" in line:
            hits.append(f"第{idx}行含加粗符号")
        if re.match(r"^#{1,6}\s+", line):
            hits.append(f"第{idx}行含Markdown标题")
        if re.match(r"^\d+\.\s+", line):
            hits.append(f"第{idx}行含编号列表")
        if re.match(r"^-\s+", line):
            hits.append(f"第{idx}行含项目列表")
        if EMOJI_RE.search(line):
            hits.append(f"第{idx}行含emoji")
    return hits


def _detect_system_prompt_lines(lines: list[str]) -> int:
    return sum(1 for line in lines if line.strip().startswith("【") and "】" in line)


def _detect_system_explanation(paragraphs: list[str]) -> list[str]:
    hits: list[str] = []
    for i, para in enumerate(paragraphs[:-1]):
        if "【" not in para or "】" not in para:
            continue
        next_para = paragraphs[i + 1]
        if any(next_para.startswith(cue) for cue in EXPLANATION_CUES):
            hits.append("系统提示后紧跟解释句")
    return hits


def _detect_single_para_run(paragraphs: list[str]) -> int:
    max_run = 0
    current = 0
    for para in paragraphs:
        sentence_count = len(_split_sentences(para))
        if sentence_count == 1:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def _detect_near_length_runs(paragraphs: list[str]) -> list[int]:
    lengths = [len(p.replace("\n", "").strip()) for p in paragraphs]
    runs: list[int] = []
    current = 1
    for i in range(1, len(lengths)):
        if abs(lengths[i] - lengths[i - 1]) <= 3:
            current += 1
        else:
            if current >= 3:
                runs.append(current)
            current = 1
    if current >= 3:
        runs.append(current)
    return runs


def _detect_short_para_window(paragraphs: list[str], window_chars: int = 200, short_limit: int = 8) -> int:
    max_count = 0
    lengths = [len(p.replace("\n", "").strip()) for p in paragraphs]
    for i in range(len(lengths)):
        total = 0
        count = 0
        for j in range(i, len(lengths)):
            total += lengths[j]
            if lengths[j] <= short_limit:
                count += 1
            if total >= window_chars:
                break
        max_count = max(max_count, count)
    return max_count


def _detect_short_queue(paragraphs: list[str], short_limit: int = 12, run_limit: int = 3) -> list[str]:
    hits: list[str] = []
    run: list[int] = []
    for idx, para in enumerate(paragraphs, start=1):
        para_len = len(para.replace("\n", "").strip())
        if para_len <= short_limit:
            run.append(idx)
        else:
            if len(run) >= run_limit:
                hits.append(f"第{run[0]}-{run[-1]}段为连续短句排队")
            run = []
    if len(run) >= run_limit:
        hits.append(f"第{run[0]}-{run[-1]}段为连续短句排队")
    return hits


def _detect_parallel(sentences: list[str]) -> list[str]:
    hits: list[str] = []
    # 明确模式
    if len(re.findall(r"不是[^。！？!?]{0,30}而是", "。".join(sentences))) > 1:
        hits.append("“不是……而是……”超线")
    if len(re.findall(r"这不仅[^。！？!?]{0,30}而且", "。".join(sentences))) > 0:
        hits.append("出现“这不仅……而且……”")
    if len(re.findall(r"不是因为[^。！？!?]{0,30}而是因为", "。".join(sentences))) > 0:
        hits.append("出现“不是因为X，而是因为Y”")

    # 粗略检测连续同结构起句
    starters = []
    for sent in sentences:
        normalized = re.sub(r'^[“"（(【\[]+', "", sent)
        starters.append(normalized[:4])
    run = 1
    for i in range(1, len(starters)):
        if starters[i] and starters[i] == starters[i - 1] and len(starters[i].strip()) >= 2:
            run += 1
        else:
            if run >= 3:
                hits.append("出现连续3句以上同结构起句")
            run = 1
    if run >= 3:
        hits.append("出现连续3句以上同结构起句")
    return hits


def _detect_action_tutorial(paragraphs: list[str]) -> list[str]:
    hits: list[str] = []
    pattern = re.compile(r"先.*再.*(然后|接着|于是)")
    for idx, para in enumerate(paragraphs, start=1):
        if pattern.search(para):
            hits.append(f"第{idx}段动作链过于教程化")
    return hits


def _ending_window(body: str, chars: int = 80) -> str:
    return body[-chars:] if len(body) > chars else body


def _build_avoidance_messages(blocking_hits: list[str], over_limit_items: list[str]) -> list[str]:
    advice: list[str] = []
    all_items = blocking_hits + over_limit_items
    mapping = [
        ("系统", "减少系统显性提示次数，提示后不要立刻解释，改成让动作接住。"),
        ("短句", "合并连续短段，别再用“短句+空行”排队砸信息。"),
        ("单句段", "打散连续单句段，至少插入动作段或混合句。"),
        ("判断句", "少写“原来、果然、意思就是”这类替读者整理的句子。"),
        ("宣传腔", "把抽象意义词改成具体动作和具体后果。"),
        ("模糊归因", "小说正文里不要再用“专家认为、有人指出”一类说明文腔。"),
        ("排比", "把工整排比打散，保留最有力的一句就够。"),
        ("破折号", "不用破折号制造气势，改回逗号、句号和动作承接。"),
        ("格式", "正文不要出现标题、列表、加粗、emoji 或 markdown 痕迹。"),
        ("动作链", "动作允许失手、误碰、返工，不要写成标准教程步骤。"),
    ]
    for key, value in mapping:
        if any(key in item for item in all_items) and value not in advice:
            advice.append(value)
    if not advice:
        advice.append("保留剧情节点，重生语言层，优先打散工整感和解释感。")
    return advice[:5]


def _prioritize_rewrite_reasons(items: list[str]) -> list[str]:
    """只保留少量高优先级问题，避免把整份清单重新喂回生成器。"""
    priority_keywords = [
        "系统",
        "短句",
        "单句段",
        "判断句",
        "动作链",
        "宣传腔",
        "模糊归因",
        "排比",
        "格式",
        "章末",
        "AI腔控制分过低",
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for keyword in priority_keywords:
        for item in items:
            if keyword in item and item not in seen:
                ordered.append(item)
                seen.add(item)
    for item in items:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered[:5]


def run_gate(project_root: Path, chapter: int) -> dict[str, Any]:
    chapter = _resolve_chapter(project_root, chapter)
    chapter_file = find_chapter_file(project_root, chapter)
    if chapter_file is None or not chapter_file.is_file():
        raise FileNotFoundError(f"未找到第{chapter}章正文文件")

    _, body, lines = _read_manuscript(chapter_file)
    paragraphs = _split_paragraphs(body)
    sentences = _split_sentences(body)

    banned_hits = _count_occurrences(body, LEVEL1_BANNED)
    weak_hits = _count_occurrences(body, WEAK_ADVERBS)
    judgement_hits = _count_occurrences(body, JUDGEMENT_PATTERNS)
    template_hits = _count_occurrences(body, TEMPLATE_ACTIONS)
    promo_hits = _count_occurrences(body, PROMO_WORDS)
    vague_hits = _count_occurrences(body, VAGUE_ATTRS)
    chat_hits = _count_occurrences(body, CHAT_TRACES)
    disclaimer_hits = _count_occurrences(body, DISCLAIMERS)
    format_hits = _detect_markdown_pollution(lines)
    system_lines = _detect_system_prompt_lines(lines)
    system_expl_hits = _detect_system_explanation(paragraphs)
    max_single_run = _detect_single_para_run(paragraphs)
    near_length_runs = _detect_near_length_runs(paragraphs)
    short_para_window = _detect_short_para_window(paragraphs)
    short_queue_hits = _detect_short_queue(paragraphs)
    parallel_hits = _detect_parallel(sentences)
    action_tutorial_hits = _detect_action_tutorial(paragraphs)
    ending_text = _ending_window(body)

    blocking_hits: list[str] = []
    over_limit_items: list[str] = []
    score = 100

    if banned_hits:
        blocking_hits.append("一级禁用词/模板动作未替换：" + "、".join(f"{k}×{v}" for k, v in banned_hits.items()))
    if any(phrase in ending_text for phrase in ENDING_SUMMARIES):
        blocking_hits.append("章末总结体/升华体")
    if short_queue_hits:
        blocking_hits.extend(short_queue_hits)
    if system_lines > 2:
        blocking_hits.append(f"系统提示累计超过2次（当前 {system_lines} 行）")
    blocking_hits.extend(system_expl_hits)
    blocking_hits.extend(action_tutorial_hits)
    if format_hits:
        blocking_hits.extend(format_hits)
    if chat_hits:
        blocking_hits.append("正文出现协作交流痕迹：" + "、".join(f"{k}×{v}" for k, v in chat_hits.items()))
    if disclaimer_hits:
        blocking_hits.append("正文出现资料不足/知识截止免责声明：" + "、".join(f"{k}×{v}" for k, v in disclaimer_hits.items()))

    # Weak adverbs
    weak_total = sum(weak_hits.values())
    if weak_total > max(3, len(body) // 1000 * 3 + 3):
        over_limit_items.append("弱化副词高频超线：" + "、".join(f"{k}×{v}" for k, v in weak_hits.items()))
        score -= 5
    for k, v in weak_hits.items():
        if v >= 2:
            over_limit_items.append(f"弱化副词重复：{k}×{v}")
            score -= 5

    # Judgement
    judgement_total = sum(judgement_hits.values())
    if judgement_total > 2:
        over_limit_items.append("判断句高频超线：" + "、".join(f"{k}×{v}" for k, v in judgement_hits.items()))
        score -= 5
    for k, v in judgement_hits.items():
        if v >= 2:
            over_limit_items.append(f"判断句重复：{k}×{v}")
            score -= 5
    if any(k in ending_text for k in JUDGEMENT_PATTERNS):
        over_limit_items.append("章末出现判断句")
        score -= 5

    # Template actions
    for k, v in template_hits.items():
        if v >= 2:
            over_limit_items.append(f"模板动作重复：{k}×{v}")
            score -= 5

    # Rhythm
    if max_single_run >= 4:
        over_limit_items.append(f"连续单句段过多：最长 {max_single_run} 段")
        score -= 4
    if near_length_runs:
        over_limit_items.append("段落长度过于接近：" + "、".join(str(x) for x in near_length_runs))
        score -= 4
    if short_para_window >= 4:
        over_limit_items.append(f"200字内短段过多：{short_para_window} 个")
        score -= 4

    # Promo / vague / parallel / dash
    if promo_hits:
        over_limit_items.append("宣传腔/意义膨胀：" + "、".join(f"{k}×{v}" for k, v in promo_hits.items()))
        score -= 5
    if vague_hits:
        over_limit_items.append("模糊归因：" + "、".join(f"{k}×{v}" for k, v in vague_hits.items()))
        score -= 6
    if parallel_hits:
        over_limit_items.extend(parallel_hits)
        score -= 6
    dash_count = body.count("—")
    if dash_count > 1:
        over_limit_items.append(f"破折号过密：{dash_count} 个")
        score -= 4

    # Explanation clusters rough
    explanation_cluster_count = 0
    for para in paragraphs:
        hits_in_para = sum(1 for cue in EXPLANATION_CUES if cue in para)
        if hits_in_para >= 2:
            explanation_cluster_count += 1
    if explanation_cluster_count:
        over_limit_items.append(f"解释句成片出现：{explanation_cluster_count} 处")
        score -= 6 * explanation_cluster_count

    status = "pass"
    rewrite_reasons: list[str] = []
    if blocking_hits:
        status = "rewrite_required"
        rewrite_reasons.extend(blocking_hits)
    if score < 88:
        status = "rewrite_required"
        rewrite_reasons.append(f"AI腔控制分过低：{score}")
    if over_limit_items:
        status = "rewrite_required"
        rewrite_reasons.extend(over_limit_items)

    # 去重保序
    seen: set[str] = set()
    rewrite_reasons = [item for item in rewrite_reasons if not (item in seen or seen.add(item))]
    rewrite_reasons = _prioritize_rewrite_reasons(rewrite_reasons)
    avoid_next_round = _build_avoidance_messages(blocking_hits, over_limit_items)

    prev_gate = read_json_safe(project_root / ".webnovel" / "tmp" / f"ch{chapter:04d}_gate_result.json", {})
    rewrite_round = int(prev_gate.get("rewrite_round") or 0) + 1

    payload = {
        "chapter": chapter,
        "chapter_file": str(chapter_file),
        "status": status,
        "blocking_hits": blocking_hits,
        "ai_style_score": max(score, 0),
        "over_limit_items": over_limit_items,
        "rewrite_reasons": rewrite_reasons,
        "avoid_next_round": avoid_next_round,
        "rewrite_round": rewrite_round,
        "next_action": "commit" if status == "pass" else "regenerate",
        "stats": {
            "chars": len(body),
            "paragraphs": len(paragraphs),
            "system_prompt_lines": system_lines,
            "max_single_para_run": max_single_run,
            "near_length_runs": near_length_runs,
            "short_para_window_le8_in_200chars": short_para_window,
        },
        "matches": {
            "level1_banned": banned_hits,
            "weak_adverbs": weak_hits,
            "judgement": judgement_hits,
            "template_actions": template_hits,
            "promo_words": promo_hits,
            "vague_attribution": vague_hits,
            "chat_traces": chat_hits,
            "disclaimers": disclaimer_hits,
            "format_pollution": format_hits,
            "parallel_hits": parallel_hits,
            "system_explanation_hits": system_expl_hits,
            "action_tutorial_hits": action_tutorial_hits,
            "short_queue_hits": short_queue_hits,
        },
    }
    return payload


def _write_scan_report(project_root: Path, payload: dict[str, Any]) -> Path:
    chapter = int(payload["chapter"])
    out_path = project_root / ".webnovel" / "tmp" / f"ch{chapter:04d}_anti_ai_scan.md"
    lines = [
        f"# 第{chapter}章 AI味扫描结果",
        "",
        "## 结论",
        f"- 状态：{payload['status']}",
        f"- AI腔控制分：{payload['ai_style_score']}",
        f"- 下一步：{payload['next_action']}",
        "",
        "## 一级拦截命中",
    ]
    blocking = payload.get("blocking_hits") or []
    if blocking:
        lines.extend(f"- {item}" for item in blocking)
    else:
        lines.append("- 无")

    lines.extend(["", "## 超线项"])
    over_limit = payload.get("over_limit_items") or []
    if over_limit:
        lines.extend(f"- {item}" for item in over_limit)
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
            "## 统计",
            f"- 字数：{payload['stats']['chars']}",
            f"- 段落数：{payload['stats']['paragraphs']}",
            f"- 系统提示行数：{payload['stats']['system_prompt_lines']}",
            f"- 连续单句段最大值：{payload['stats']['max_single_para_run']}",
            f"- 200字内短段峰值：{payload['stats']['short_para_window_le8_in_200chars']}",
            "",
            "## 下轮必须避免",
        ]
    )
    lines.extend(f"- {item}" for item in payload.get("avoid_next_round") or ["无"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _write_rewrite_notes(project_root: Path, payload: dict[str, Any]) -> Path | None:
    if payload["status"] != "rewrite_required":
        return None
    chapter = int(payload["chapter"])
    out_path = project_root / ".webnovel" / "tmp" / f"ch{chapter:04d}_rewrite_notes.md"
    lines = [
        f"# 第{chapter}章打回说明",
        "",
        "## 本轮结论",
        "- 状态：rewrite_required",
        f"- AI腔控制分：{payload['ai_style_score']}",
        "",
        "## 命中问题",
    ]
    lines.extend(f"- {item}" for item in payload.get("rewrite_reasons") or ["无"])
    lines.extend(["", "## 下轮必须避免"])
    lines.extend(f"- {item}" for item in payload.get("avoid_next_round") or ["无"])
    lines.extend(
        [
            "",
            "## 允许保留",
            "- 本章剧情节点不变",
            "- 本章结果不变",
            "- 本章章末钩子不变",
        ]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="章节 AI 高频次 gate")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    parser.add_argument("--chapter", type=int, default=0, help="目标章节号；默认 current_chapter + 1")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    project_root = resolve_project_root(args.project_root)
    payload = run_gate(project_root, args.chapter)
    scan_path = _write_scan_report(project_root, payload)
    gate_path = project_root / ".webnovel" / "tmp" / f"ch{int(payload['chapter']):04d}_gate_result.json"
    atomic_write_json(gate_path, payload, backup=False)
    rewrite_path = _write_rewrite_notes(project_root, payload)

    result = {
        "chapter": payload["chapter"],
        "status": payload["status"],
        "scan_report": str(scan_path),
        "gate_result": str(gate_path),
        "rewrite_notes": str(rewrite_path) if rewrite_path else "",
        "ai_style_score": payload["ai_style_score"],
        "next_action": payload["next_action"],
    }
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"chapter: {result['chapter']}")
        print(f"status: {result['status']}")
        print(f"ai_style_score: {result['ai_style_score']}")
        print(f"next_action: {result['next_action']}")
        print(f"scan_report: {result['scan_report']}")
        print(f"gate_result: {result['gate_result']}")
        if result["rewrite_notes"]:
            print(f"rewrite_notes: {result['rewrite_notes']}")


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
