#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网文项目初始化脚本

目标：
- 生成可运行的项目结构（webnovel-project）
- 创建/更新 .webnovel/state.json（运行时真相）
- 生成基础设定集与大纲模板文件（供 /webnovel-plan、/webnovel-chapter 与 /webnovel-write 使用）

说明：
- 该脚本是命令 /webnovel-init 的“唯一允许的文件生成入口”（与命令文档保持一致）。
- 生成的内容以“模板骨架”为主，便于 AI/作者后续补全；但保证所有关键文件存在。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio
from typing import Any, Dict, List
import re

# 安全修复：导入安全工具函数
from security_utils import sanitize_commit_message, atomic_write_json, is_git_available
from project_locator import write_current_project_pointer


# Windows 编码兼容性修复
if sys.platform == "win32":
    enable_windows_utf8_stdio()


_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")


def _validate_initial_genre_source(genre: str) -> str:
    normalized = str(genre or "").strip()
    if _ASCII_LETTER_RE.search(normalized):
        raise SystemExit(
            "题材必须使用中文名称，不能使用英文 profile key "
            f"'{normalized}'。例如：规则怪谈、悬疑、玄幻。"
        )
    return normalized


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_text_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")


def _split_genre_keys(genre: str) -> list[str]:
    raw = (genre or "").strip()
    if not raw:
        return []
    # 支持复合题材：A+B / A+B / A、B / A与B
    raw = re.sub(r"[＋/、]", "+", raw)
    raw = raw.replace("与", "+")
    parts = [p.strip() for p in raw.split("+") if p.strip()]
    return parts or [raw]


def _normalize_genre_key(key: str) -> str:
    aliases = {
        "修仙/玄幻": "修仙",
        "玄幻修仙": "修仙",
        "玄幻": "修仙",
        "修真": "修仙",
        "都市修真": "都市异能",
        "都市高武": "高武",
        "都市奇闻": "都市脑洞",
        "古言脑洞": "古言",
        "游戏电竞": "电竞",
        "电竞文": "电竞",
        "直播": "直播文",
        "直播带货": "直播文",
        "主播": "直播文",
        "克系": "克苏鲁",
        "克系悬疑": "克苏鲁",
    }
    return aliases.get(key, key)


def _apply_label_replacements(text: str, replacements: Dict[str, str]) -> str:
    if not text or not replacements:
        return text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        for label, value in replacements.items():
            if not value:
                continue
            prefix = f"- {label}："
            if stripped.startswith(prefix):
                leading = line[: len(line) - len(stripped)]
                lines[i] = f"{leading}{prefix}{value}"
    return "\n".join(lines)


def _parse_tier_map(raw: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not raw:
        return result
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, val = part.split(":", 1)
            result[key.strip()] = val.strip()
    return result


def _needs_protagonist_group(protagonist_structure: str) -> bool:
    text = (protagonist_structure or "").strip()
    return any(marker in text for marker in ("主角组", "双主角", "多主角", "群像主角"))


def _needs_heroine_card(heroine_config: str, heroine_names: str) -> bool:
    text = (heroine_config or "").strip().lower()
    if text in {"无", "无女主", "none", "no heroine"}:
        return False
    return bool((heroine_names or "").strip() or text)


def _render_team_rows(names: List[str], roles: List[str]) -> List[str]:
    rows = []
    for idx, name in enumerate(names):
        role = roles[idx] if idx < len(roles) else ""
        rows.append(f"| {name} | {role or '主线/副线'} | | | |")
    return rows


def _ensure_state_schema(state: Dict[str, Any]) -> Dict[str, Any]:
    """确保 state.json 具备 v5.1 架构所需的字段集合（v5.4 沿用）。

    v5.1 变更:
    - entities_v3 和 alias_index 已迁移到 index.db，不再存储在 state.json
    - structured_relationships 已迁移到 index.db relationships 表
    - state.json 保持精简 (< 5KB)
    """
    state.setdefault("project_info", {})
    state.setdefault("progress", {})
    state.setdefault("protagonist_state", {})
    state.setdefault("relationships", {})  # update_state.py 需要此字段
    state.setdefault("disambiguation_warnings", [])
    state.setdefault("disambiguation_pending", [])
    state.setdefault("world_settings", {"power_system": [], "factions": [], "locations": []})
    state.setdefault("plot_threads", {"active_threads": [], "foreshadowing": []})
    state.setdefault("review_checkpoints", [])
    state.setdefault("chapter_meta", {})
    state.setdefault(
        "strand_tracker",
        {
            "last_quest_chapter": 0,
            "last_fire_chapter": 0,
            "last_constellation_chapter": 0,
            "current_dominant": "quest",
            "chapters_since_switch": 0,
            "history": [],
        },
    )
    # v5.1: entities_v3, alias_index, structured_relationships 已迁移到 index.db
    # 不再在 state.json 中初始化这些字段

    # progress schema evolution
    state["progress"].setdefault("current_chapter", 0)
    state["progress"].setdefault("total_words", 0)
    state["progress"].setdefault("last_updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    state["progress"].setdefault("volumes_completed", [])
    state["progress"].setdefault("current_volume", 1)
    state["progress"].setdefault("volumes_planned", [])

    # protagonist schema evolution
    ps = state["protagonist_state"]
    ps.setdefault("name", "")
    ps.setdefault("power", {"realm": "", "layer": 1, "bottleneck": ""})
    ps.setdefault("location", {"current": "", "last_chapter": 0})
    ps.setdefault("golden_finger", {"name": "", "level": 1, "cooldown": 0, "skills": []})
    ps.setdefault("attributes", {})

    return state


def _build_master_outline(target_chapters: int, *, chapters_per_volume: int = 50) -> str:
    volumes = (target_chapters - 1) // chapters_per_volume + 1 if target_chapters > 0 else 1
    lines: list[str] = [
        "# 总纲",
        "",
        "> 本文件为“总纲骨架”，用于 /webnovel-plan 细化为卷大纲与章纲。",
        "",
        "## 卷结构",
        "",
    ]

    for v in range(1, volumes + 1):
        start = (v - 1) * chapters_per_volume + 1
        end = min(v * chapters_per_volume, target_chapters)
        lines.extend(
            [
                f"### 第{v}卷（第{start}-{end}章）",
                "- 核心冲突：",
                "- 关键爽点：",
                "- 卷末高潮：",
                "- 主要登场角色：",
                "- 关键伏笔（埋/收）：",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _build_golden_three_card_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# 黄金三章作战卡",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "本卡是第1-3章硬闸，会被 NCS bridge 自动读入。正文不能把本卡写成说明，只能变成现场压力、动作、伤口、物件、选择和章末钩子。",
            "",
            "## 番茄开篇硬标准",
            "",
            "- 不把铺垫当故事。第一句就要把读者推到危险现场，不能先写醒来、回忆、日常、天气、世界观或情绪铺垫。",
            "- 前300字必须完成冲突爆发：见血、见尸、见异变、见亲人反常、见身份被夺，至少命中两项。",
            "- 前300字必须露出本书高刺激关键词：主角困境、核心威胁、关系压迫、金手指/能力边界、死亡或失去风险。",
            "- 前三章每章只围绕一个主场景打穿，不频繁换场，不写短篇式谜面收束；每章都要把读者推向下一章更大的动作。",
            "- 每章必须有一个能被读者复述的名场面，一句能截图传播的狠话或反常动作，一个可见小赢面，一个可见代价。",
            "- 主角不能靠解释取胜。他必须少说、错位、试探、交易、伤自己或放弃某个安全选项。",
            "- 章末不能只留谜语，必须留下“下一章非看不可”的现实动作：人要被抬走、名要被写上、门要被关、关系要被迫表态。",
            "",
            "## AI味硬杀",
            "",
            "- 禁止被动惊醒模板：`X是被Y弄醒的`、`X醒来时发现自己被...`、`一睁眼...`式默认开局。",
            "- 禁止合同履约腔：把“钩子、爽点、代价、章末钩子”按顺序翻译成段落。",
            "- 禁止解释型规则：规则必须通过物件、伤口、动作、失去和选择造成后果。",
            "- 禁止情绪先行的慢热：不能先写悲伤、迷茫、震惊，再让冲突发生；冲突先砸下来，情绪从反应里长出来。",
            "- 禁止短篇反转收束：前三章不是讲完一个小故事，而是打开长篇主线的第一扇门。",
            "",
            "## 第1章",
            "",
            "- 任务：第一屏完成核心困境，让读者知道主角现在不动就会失去什么。",
            "- 第一句目标：直接出现危险、异常关系、死亡/失去风险或核心卖点中的至少两项，不用醒来模板。",
            "- 前300字必有：主角被迫面对核心危险；身边人/物给出反常压力；本书核心卖点露面；主角不能靠解释脱身。",
            "- 名场面：一个能让读者截图复述的狠动作、狠话或反常选择。",
            "- 小赢面：主角靠现场判断躲过第一次致命钩子。",
            "- 可见代价：身体、关系、资源、名声、记忆或安全感至少损失一项。",
            "- 章末强钩：下一章必须立刻承接的现实动作。",
            "",
            "## 第2章",
            "",
            "- 任务：承接第1章钩子并升压，不复述局势，不停下来讲规则。",
            "- 前300字必有：第1章章末压力继续逼近；主角的可选项更少；关系或敌人把他往更危险身份里推。",
            "- 名场面：重要关系第一次递进，读者更清楚谁在害他、谁在用痛苦保护他、谁在逼他犯错。",
            "- 小赢面：主角用错位身份、反向选择或代价交换赢半步。",
            "- 可见代价：第1章代价升级或转嫁到重要关系上。",
            "- 章末强钩：第3章必须完成第一次小兑现。",
            "",
            "## 第3章",
            "",
            "- 任务：完成前三章第一次小兑现，同时打开长篇主线。",
            "- 前300字必有：第2章章末风险当场兑现，敌人/规则拿到更大筹码。",
            "- 名场面：反派或规则完成一次压迫性胜利，主角必须放弃短期安全换长期破局线。",
            "- 小赢面：主角不是赢局面，而是抢到下一阶段行动资格或关键物证/线索。",
            "- 不可逆选择：主角离开舒适区或失去一个不能立刻补回的东西。",
            "- 章末强钩：第4章必须行动，不是继续站着解释。",
            "",
            "## 打回规则",
            "",
            "- 前300字没有冲突爆发，打回。",
            "- 第一章开头先醒来、先日常、先解释、先铺情绪，打回。",
            "- 前三章任一章没有名场面、小赢面、可见代价、章末动作钩，打回。",
            "- 主角靠解释、喊冤、自证身份取胜，打回。",
            "- 读完像传统慢热铺垫，而不是平台高刺激长篇开局，打回。",
            "",
        ]
    )


def _build_writing_workflow_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# 写作流程",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "## 目标",
            "",
            "这套流程把 `webnovel-writer` 的资料库、状态追踪、面板和 Novel-Control-Station/No 的正文质感接起来。",
            "",
            "- 正式创作单章时，外层入口使用 `/webnovel-writer:webnovel-chapter [章节号]`。",
            "- `webnovel-writer` 负责项目结构、角色/物品/技能卡、时间线、合同树、写后提交和面板展示。",
            "- Novel-Control-Station/No 只负责正文质感和现场感，不自由改设定。",
            "- 本项目的 `.codex/skills/no-webnovel-write` 是约束层，不替代 `/webnovel-writer:webnovel-chapter`。",
            "- `$anti-ai-rewrite` 只做终检和去模板腔，不替代写前合同和状态更新。",
            "",
            "## Init 阶段",
            "",
            "初始化必须生成：",
            "",
            "- `.webnovel/state.json`",
            "- `.story-system/` 合同树目录",
            "- `设定集/角色库/`",
            "- `设定集/技能卡/`",
            "- `设定集/物品库/`",
            "- `大纲/剧情时间轴.md`",
            "- `设定集/技能物品时间线.md`",
            "- `大纲/总纲.md`",
            "- `大纲/爽点规划.md`",
            "- `大纲/黄金三章作战卡.md`",
            "- `规划/写作流程.md`",
            "- `规划/No正文生成提示词.md`",
            "- `.webnovel/post_chapter_update_checklist.md`",
            "- `.codex/skills/no-webnovel-write/SKILL.md`",
            "",
            "## Plan 阶段",
            "",
            "当前卷写作前必须具备：",
            "",
            "- 当前卷详细大纲",
            "- 当前卷时间线",
            "- 当前卷节拍表",
            "- 全书剧情时间轴",
            "- 前期爽点或试水节奏方案",
            "- 中后期技能/物品允许方向",
            "",
            "## Chapter Contract 阶段",
            "",
            "本阶段由 `/webnovel-writer:webnovel-chapter [章节号]` 封装触发；不能绕过它直接写正文。",
            "",
            "每章写前生成当前章合同，合同缺失时不得直接写正文。",
            "",
            "第1-3章必须把 `大纲/黄金三章作战卡.md` 写入合同链路：合同、NCS bridge、现场草稿和 Review 都要标明本章承担的黄金三章任务。缺失本卡或任务不清，不得起草正文。",
            "",
            "合同至少包含：",
            "",
            "- 本章目标",
            "- 本章爽点",
            "- 出场人物",
            "- 人物当前状态",
            "- 可用技能/物品",
            "- 必须保留",
            "- 禁止写崩",
            "- 章末钩子",
            "",
            "## No 正文阶段",
            "",
            "No 正文阶段仍在 `/webnovel-writer:webnovel-chapter` 的 Step 1-2 内执行：先生成 `.webnovel/tmp/ncs-bridge/`，再通过 Novel-Control-Station/No 起草。",
            "",
            "No/NCS 负责正文质感，但必须按合同和资料库写。",
            "",
            "写正文前必须核对：",
            "",
            "- `.story-system/MASTER_SETTING.json`",
            "- 当前章合同",
            "- `设定集/OOC禁区.md`",
            "- `设定集/平台风格约束.md`",
            "- 当前卷详细大纲、时间线、节拍表",
            "- `大纲/剧情时间轴.md`",
            "- `大纲/爽点规划.md`",
            "- 第1-3章额外读取：`大纲/黄金三章作战卡.md`",
            "- `设定集/角色库/`",
            "- `设定集/技能卡/`",
            "- `设定集/物品库/`",
            "- `设定集/技能物品时间线.md`",
            "- 同人/衍生项目额外读取：`设定集/原作时间线.md`、`设定集/同人分歧点.md`",
            "",
            "## 正文口感约束",
            "",
            "- 先写现场，再让设定从现场里长出来。",
            "- 番茄前三章不允许“铺垫当故事”：第一句进危险，前300字必须冲突爆发，至少见血/见尸/见异变/见亲人反常/见身份被夺中的两项。",
            "- 前三章每章只打穿一个主场景，避免换场过多；长篇开局要留下更大动作钩，不能写成短篇谜面收束。",
            "- 开篇第一句禁止默认“被动惊醒/受害惊醒”模板，例如“某人是被某物泼醒/噎醒/砸醒的”“某人醒来时发现自己被……”。要从物件、身体反应、环境动作或人物选择直接切入。",
            "- 少替读者总结主题，少用“这不是……而是……”解释句。",
            "- 角色用动作、停顿、误判、选择体现状态，不用作者旁白替他说透。",
            "- 规则、系统、技能不能变成说明书；每次规则出现都要带来风险、代价或选择。",
            "- 每章至少有一个可感知爽点：救下、反杀、夺回、打脸、破局、身份推进、关系转折或新危机开门。",
            "- 章末钩子必须从本章事件自然长出，不靠硬抛谜语。",
            "",
            "## Review 阶段",
            "",
            "本阶段继承 `/webnovel-writer:webnovel-chapter` 封装下的 `webnovel-write` Step 3-5：`reviewer` 审查 -> NCS/anti-AI gate -> data-agent artifacts -> `chapter-commit`。不得绕过该流程改成口头评分。",
            "",
            "正文定稿前检查：",
            "",
            "- 设定是否冲突",
            "- 人物是否 OOC",
            "- 战力/能力是否越级",
            "- 爽点是否可感知",
            "- AI 腔是否明显",
            "- 技能/物品/时间线是否需要写后更新",
            "",
            "## Commit 阶段",
            "",
            "用户确认“正式”后，才进入写后提交流程。",
            "",
            "写后必须更新：",
            "",
            "- chapter summary",
            "- index.db",
            "- character_state",
            "- relationship_events",
            "- timeline_events",
            "- `大纲/剧情时间轴.md`",
            "- foreshadows",
            "- 技能卡：获得、暴露、强化、限制、反噬、冷却、伤势影响",
            "- 物品卡：持有人、位置、损坏、消耗、转移、遗失",
            "- `设定集/技能物品时间线.md`",
            "- 同人/衍生项目：原作时间线、同人分歧点",
            "- `.webnovel/state.json`",
            "",
            "写后必须执行：",
            "",
            "```text",
            ".webnovel/post_chapter_update_checklist.md",
            "```",
            "",
            "未通过时不得提交章节。",
            "",
        ]
    )


def _build_no_prompt_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# No 正文生成提示词",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "你只负责正文质感，不负责自由改动设定。",
            "",
            "## 必读",
            "",
            "请严格读取并遵守：",
            "",
            "1. `.story-system/MASTER_SETTING.json`",
            "2. 当前章合同，例如 `.story-system/chapters/chapter_005_contract.json`",
            "3. `设定集/OOC禁区.md`",
            "4. `设定集/平台风格约束.md`",
            "5. 当前卷详细大纲",
            "6. 当前卷时间线",
            "7. 当前卷节拍表",
            "8. `大纲/剧情时间轴.md`",
            "9. `大纲/爽点规划.md`",
            "10. 第1-3章额外读取：`大纲/黄金三章作战卡.md`",
            "11. `设定集/角色库/`",
            "12. `设定集/主角卡.md`",
            "13. `设定集/金手指设计.md`",
            "14. `设定集/改写边界.md`",
            "15. `设定集/技能卡/`",
            "16. `设定集/物品库/`",
            "17. `设定集/技能物品时间线.md`",
            "18. 同人/衍生项目额外读取：`设定集/原作时间线.md`",
            "19. 同人/衍生项目额外读取：`设定集/同人分歧点.md`",
            "",
            "## 正文要求",
            "",
            "- 第1-3章执行 `大纲/黄金三章作战卡.md`：第一句进危险，前300字冲突爆发，不把铺垫当故事。",
            "- 第1-3章每章必须有名场面、小赢面、可见代价和章末强动作钩。",
            "- 开局快，冲突明确，尽快把线索变成杀局、选择、反杀、身份推进或原作回流。",
            "- 禁止默认被动惊醒开头：`X是被Y弄醒的`、`X醒来时发现自己被...`、`一睁眼...`。",
            "- 不写百科复述，不写设定说明书，不写系统面板流水账。",
            "- 人物通过动作、对话、选择、沉默和误判体现状态。",
            "- 少用作者式总结句，少把主题直接说出来。",
            "- 少用过于整齐的句式：`不是……而是……`、`他明白一件事`、`这意味着……`。",
            "- 每章末尾必须有钩子，但钩子必须来自本章事件。",
            "- 主角不能无脑装逼，前期依靠信息差、代价交换、现场判断和布局。",
            "",
            "## 状态约束",
            "",
            "- 正文中的技能、血脉、法器、忍具、系统能力等，只能按当前技能卡状态使用。",
            "- 物品不能凭空出现、消失、换手、损坏或升级；出现变化必须能落到物品卡。",
            "- 角色受伤、立场、信任、敌意、同行/分离变化，必须能落到角色卡或提交事件。",
            "- 时间锚点、地点、事件结果、下一章压力，必须能落到 `大纲/剧情时间轴.md`。",
            "- 原作事件被提前、延后、保留或改写时，必须能落到原作时间线或同人分歧点。",
            "- 若本章造成技能、物品、人物关系、伤势、阵营、时间线变化，正式提交前必须执行 `.webnovel/post_chapter_update_checklist.md`。",
            "",
            "## 禁止",
            "",
            "- 不能为了爽点临时改技能、改道具、改时间线。",
            "- 不能让人物替作者解释主题。",
            "- 不能让配角只负责震惊、点头、复读设定。",
            "- 不能把规则辩论写成条款清单，必须让规则压到人的身体、选择和损失上。",
            "- 不能把前三章写成传统慢热铺垫或短篇谜面收束。",
            "",
        ]
    )


def _build_post_chapter_checklist(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# 写后状态更新清单",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "每章正文定稿后执行。未完成前不得进入最终提交。",
            "",
            "## 必读源",
            "",
            "- `设定集/角色库/`",
            "- `设定集/技能卡/`",
            "- `设定集/物品库/`",
            "- `设定集/技能物品时间线.md`",
            "- `.webnovel/state.json`",
            "- `大纲/剧情时间轴.md`",
            "- 最近 3 章正文和摘要",
            "- 同人/衍生项目额外读取：`设定集/原作时间线.md`、`设定集/同人分歧点.md`",
            "",
            "## 角色状态",
            "",
            "- [ ] 出场人物当前状态已核对。",
            "- [ ] 受伤、昏迷、消耗、情绪、立场变化已记录。",
            "- [ ] 阵营、关系、敌意、信任、同行/分离状态已更新。",
            "- [ ] 重要人物不得只在正文变化，角色卡/索引必须跟上。",
            "",
            "## 技能状态",
            "",
            "- [ ] 本章使用过的技能、血脉、法术、忍术、体术、刀术、金手指能力都已核对技能卡。",
            "- [ ] 新解锁、强化、暴露、被识破、受限、反噬、冷却、代价已更新。",
            "- [ ] 若出现新技能、组合技、阶段升级，必须先建卡或更新 `设定集/技能卡/技能卡总表.md`。",
            "- [ ] 重要技能变化已追加到 `设定集/技能物品时间线.md`。",
            "",
            "## 物品状态",
            "",
            "- [ ] 武器、道具、凭证、符纸、卷轴、法器、情报物等出现即核对物品库。",
            "- [ ] 物品位置、持有人、损坏、消耗、隐藏、转移、遗失已更新。",
            "- [ ] 新物品或计划态物品进入正文，必须先建单卡或更新 `设定集/物品库/物品卡总表.md`。",
            "- [ ] 重要物品变化已追加到 `设定集/技能物品时间线.md`。",
            "- [ ] 若只是出场但无状态变化，也要在提交输出的 `no_update_needed` 写明原因。",
            "",
            "## 时间线与事件",
            "",
            "- [ ] 本章时间锚点、地点、战斗/事件结果已同步到时间线/事件索引。",
            "- [ ] `大纲/剧情时间轴.md` 已追加本章事实记录。",
            "- [ ] 原作事件如果被提前、延后、改写、保留，已更新 `同人分歧点.md` 或相关大纲。",
            "- [ ] 若出现新势力、新任务线、新副本、新追杀线，已写入对应设定或伏笔记录。",
            "",
            "## 伏笔与债务",
            "",
            "- [ ] 新伏笔已记录：内容、种类、触发章、预计回收章。",
            "- [ ] 已回收伏笔已标记回收。",
            "- [ ] 因改写原作或改变事件结果产生的新剧情债已记录。",
            "- [ ] 不能把伏笔只藏在正文里，不进索引。",
            "",
            "## 提交前输出",
            "",
            "```text",
            "post_chapter_update_check: pass/fail",
            "updated_files:",
            "- 路径：更新原因",
            "no_update_needed:",
            "- 路径或类别：原因",
            "conflicts:",
            "- 无 / 冲突描述 + 处理方式",
            "```",
            "",
        ]
    )


def _build_skill_item_timeline_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# 技能物品时间线",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "## 用途",
            "",
            "这份文件追踪技能、能力、武器、道具和关键物品的生命周期。正文写作、章节提交和资料库更新时，用它确认：",
            "",
            "- 技能是否已经暴露给某人。",
            "- 技能是否已经升级、受限或反噬。",
            "- 物品当前持有人是谁。",
            "- 物品是否损坏、丢失、消耗、换手。",
            "- 某个能力/物品能不能在当前章节使用。",
            "",
            "## 记录字段",
            "",
            "- 名称：技能或物品名。",
            "- 类型：技能、血脉、法术、忍具、武器、法器、情报物、凭证等。",
            "- 当前持有人：角色或势力。",
            "- 当前状态：可用、受损、隐藏、暴露、失控、待回收。",
            "- 首次出现：章节。",
            "- 最近变化：章节和变化摘要。",
            "- 下一节点：计划在哪个章节或卷发生变化。",
            "- 禁区：当前阶段不能发生什么。",
            "",
            "## 生命周期表",
            "",
            "| 名称 | 类型 | 当前持有人 | 当前状态 | 首次出现 | 最近变化 | 下一节点 | 禁区 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
            "| （待填写） |  |  |  |  |  |  |  |",
            "",
            "## 中后期卷级更新总账",
            "",
            "这张表只记录“计划态”和“允许方向”，不是已经发生的正文事实。正式连载到对应章节后，才把具体变化写进上面的生命周期表和对应技能卡/物品卡。",
            "",
            "| 阶段 | 章节范围 | 技能更新重点 | 物品更新重点 | 必须防止 |",
            "| --- | --- | --- | --- | --- |",
            "| 卷一 | 第1-50章 |  |  |  |",
            "",
            "## 专项总表",
            "",
            "- 人物技能中后期更新：`设定集/技能卡/中后期人物技能更新总表.md`",
            "- 物品/道具中后期更新：`设定集/物品库/物品卡总表.md`",
            "",
            "## 更新规则",
            "",
            "- 每次正式 chapter-commit 后，如果技能或物品状态变化，必须同步更新本文件或通过资料库事件投影更新。",
            "- 草稿阶段可以不更新，但一旦用户确认“正式”，需要把本章出现过的技能、物品状态写入提交事件。",
            "- 若能力升级，必须注明升级原因、代价和首次验证章节。",
            "- 若物品换手，必须注明交接场景和关系后果。",
            "- 中后期计划只能写“允许方向”，不能当成正文事实；写到对应章节后再把“计划态”改成“已发生”。",
            "",
        ]
    )


def _build_story_timeline_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# 剧情时间轴",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "## 用途",
            "",
            "这份文件是写后更新用的全书事件时间轴。卷级 `第N卷-时间线.md` 负责计划，本文件负责记录已经发生的正文事实。",
            "",
            "每章正式提交后，如果发生事件推进、地点变化、时间跳转、人物状态变化、技能/物品变化、伏笔埋收或原作分歧，都必须追加一条记录。",
            "",
            "## 记录字段",
            "",
            "- 章节：第几章。",
            "- 时间锚点：故事内日期、时辰、任务日、末世第几天、考试第几场等。",
            "- 地点：主场景或移动路线。",
            "- 核心事件：本章发生了什么，必须是正文事实。",
            "- 结果变化：赢了什么、失去了什么、身份/局势/关系怎么变。",
            "- 人物状态：伤势、立场、同行/分离、情绪、信任/敌意。",
            "- 技能/物品变化：引用 `设定集/技能物品时间线.md` 的对应条目。",
            "- 伏笔变化：新埋、推进、回收、失效。",
            "- 下一章压力：下一章必须承接的危机或问题。",
            "",
            "## 全书时间轴表",
            "",
            "| 章节 | 时间锚点 | 地点 | 核心事件 | 结果变化 | 人物状态 | 技能/物品变化 | 伏笔变化 | 下一章压力 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            "| （待填写） |  |  |  |  |  |  |  |  |",
            "",
            "## 更新规则",
            "",
            "- 只记录已经发生的正文事实，不把中后期计划写成既成事实。",
            "- 时间锚点必须单调可追踪；若倒叙、梦境、回忆或双时间线，必须注明叙事时间和事件实际时间。",
            "- 若章节改变原作节点、提前/延后事件或制造同人分歧，还要同步更新 `设定集/原作时间线.md` 或 `设定集/同人分歧点.md`。",
            "- 若章节改变技能/物品状态，还要同步更新 `设定集/技能物品时间线.md`。",
            "- 若时间线冲突，先修正文或合同，不要为了正文强行改时间轴。",
            "",
        ]
    )


def _build_skill_index_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# 技能卡总表",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "| 技能/能力 | 持有人 | 阶段 | 状态 | 首次出现 | 最近变化 | 单卡路径 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            "| （待填写） |  |  |  |  |  |  |",
            "",
            "## 使用规则",
            "",
            "- 正文使用任何新技能前，先建技能卡或登记到本表。",
            "- 技能升级、暴露、被识破、冷却、反噬都必须更新。",
            "- 单卡建议放在 `设定集/技能卡/{角色}-{技能名}.md`。",
            "",
        ]
    )


def _build_mid_late_skill_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# 中后期人物技能更新总表",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "这份表约束中后期人物技能成长，避免战力漂移、升级突兀、原作人物/核心配角被削弱。",
            "",
            "| 角色 | 当前阶段 | 允许成长方向 | 禁止提前获得 | 预计节点 |",
            "| --- | --- | --- | --- | --- |",
            "| （待填写） |  |  |  |  |",
            "",
            "## 更新规则",
            "",
            "- 角色技能状态变化后，要同步更新 `设定集/技能物品时间线.md`。",
            "- 中后期计划不能当成当前正文事实使用。",
            "",
        ]
    )


def _build_item_index_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# 物品卡总表",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "| 物品 | 类型 | 当前持有人 | 当前状态 | 首次出现 | 最近变化 | 单卡路径 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            "| （待填写） |  |  |  |  |  |  |",
            "",
            "## 使用规则",
            "",
            "- 正文使用任何重要物品前，先建物品卡或登记到本表。",
            "- 持有人、位置、损坏、消耗、隐藏、转移、遗失都必须更新。",
            "- 单卡建议放在 `设定集/物品库/{物品名}.md`。",
            "",
        ]
    )


def _build_simple_policy_doc(title: str, genre: str, now: str, kind: str) -> str:
    if kind == "ooc":
        body = [
            "# OOC禁区",
            "",
            "## 通用原则",
            "",
            "- 角色不能为了推进剧情突然降智。",
            "- 角色不能突然替作者解释主题。",
            "- 原作/既有角色的能力、性格、关系压力必须先核对资料库。",
            "- 主角不能靠临时外挂无代价碾压。",
            "",
            "## 待补角色禁区",
            "",
            "| 角色 | 不能做什么 | 原因 |",
            "| --- | --- | --- |",
            "| （待填写） |  |  |",
        ]
    elif kind == "platform":
        body = [
            "# 平台风格约束",
            "",
            "## 通用节奏",
            "",
            "- 开局尽快给冲突、危机、选择或反杀。",
            "- 前30章按试水节奏处理，线索不能长期只做谜语。",
            "- 每章至少一个可感知爽点，每 3-5 章一次更强结果。",
            "- 设定可以复杂，但读者每章必须知道主角赢了什么、失去了什么、下一步为什么危险。",
            "",
            "## 禁止",
            "",
            "- 长段百科说明。",
            "- 纯规则辩论无身体代价。",
            "- 只埋伏笔不兑现当前阅读快感。",
        ]
    else:
        body = [
            "# 改写边界",
            "",
            "## 允许",
            "",
            "- 调整表达、节奏、场景顺序和动作细节。",
            "- 加强现场感、冲突和可感知爽点。",
            "- 在不改变事实的前提下压掉 AI 腔。",
            "",
            "## 禁止",
            "",
            "- 未经确认改主线结局。",
            "- 未经确认改角色核心动机。",
            "- 未经确认新增高阶技能、关键道具或时间线事实。",
            "- 为了爽点临时削弱强角色或让反派降智。",
        ]

    return "\n".join([body[0], "", f"> 项目：{title}｜题材：{genre}｜创建：{now}", *body[2:], ""])


def _build_optional_fanfic_doc(title: str, genre: str, now: str, kind: str) -> str:
    if kind == "source_timeline":
        return "\n".join(
            [
                "# 原作时间线",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "非同人/非衍生项目可留空。同人/衍生项目必须用本文件约束原作节点。",
                "",
                "| 原作节点 | 原作时间 | 当前处理 | 改写影响 | 关联章节 |",
                "| --- | --- | --- | --- | --- |",
                "| （待填写） |  | 保留/提前/延后/改写 |  |  |",
                "",
            ]
        )
    return "\n".join(
        [
            "# 同人分歧点",
            "",
            f"> 项目：{title}｜题材：{genre}｜创建：{now}",
            "",
            "非同人/非衍生项目可留空。同人/衍生项目必须记录每次改写原作带来的后果。",
            "",
            "| 分歧点 | 发生章节 | 原作结果 | 本书结果 | 后续剧情债 |",
            "| --- | --- | --- | --- | --- |",
            "| （待填写） |  |  |  |  |",
            "",
        ]
    )


def _build_codex_no_skill_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "---",
            "name: no-webnovel-write",
            "description: Use when writing or continuing this webnovel-writer book with Novel-Control-Station/No as the prose engine, while preserving the dashboard, cards, timeline, story-system contracts, and chapter commit flow.",
            "---",
            "",
            "# No Webnovel Write",
            "",
            f"> Project: {title}｜Genre: {genre}｜Initialized: {now}",
            "",
            "## Intent",
            "",
            "Use No/NCS only as the prose engine. Keep webnovel-writer as the control station for:",
            "",
            "- project binding and book switching",
            "- dashboard and menus",
            "- character cards, skill cards, item cards, and setting files",
            "- outlines, timelines, beat sheets, summaries, memory, and index.db",
            "- reviewer, data-agent, chapter-commit, and projection updates",
            "",
            "Do not replace the existing panel or information-card system.",
            "",
            "## Relationship To /chapter",
            "",
            "- For normal official chapter creation, the outer entry is `/webnovel-writer:webnovel-chapter [chapter_num]`.",
            "- This local `no-webnovel-write` skill is the project constraint/adaptation layer, not a replacement for `/webnovel-writer:webnovel-chapter`.",
            "- `/webnovel-writer:webnovel-chapter` prepares the chapter contract, builds the NCS bridge, runs the write/review/commit chain, and updates projection.",
            "- This skill adds this book's fresh-run rules: old manuscript isolation, No/NCS as prose engine only, source-first prose gate, anti-AI taste gate, and stricter current-artifact requirements.",
            "- Do not run an ad hoc manual chapter flow just because this local skill exists.",
            "",
            "## Required Source",
            "",
            "Before drafting, locate the sibling Novel-Control-Station-Skill. Prefer these paths in order:",
            "",
            "1. `../Novel-Control-Station-Skill/SKILL.md`",
            "2. `../../Novel-Control-Station-Skill/SKILL.md`",
            "3. `/Users/liangfushou/project/小说/new/Novel-Control-Station-Skill/SKILL.md`",
            "",
            "For de-AI cleanup, load the NCS authenticity/de-AI reference only when needed.",
            "",
            "If present, also load:",
            "",
            "- `/Users/liangfushou/project/小说/new/webnovel-writer/webnovel-writer/skills/webnovel-chapter/SKILL.md`",
            "- `/Users/liangfushou/project/小说/new/webnovel-writer/webnovel-writer/skills/webnovel-write/SKILL.md`",
            "- `/Users/liangfushou/project/小说/new/webnovel-writer/webnovel-writer/skills/anti-ai-rewrite/SKILL.md`",
            "- `.webnovel/anti_ai_rewrite_manual.md`",
            "- `.webnovel/anti_ai_checklist.md`",
            "- `.webnovel/post_chapter_update_checklist.md`",
            "- `规划/写作流程.md`",
            "- `规划/No正文生成提示词.md`",
            "- `大纲/黄金三章作战卡.md`（第1-3章必读；缺失则不得起草前三章）",
            "- `大纲/前期爽点重写方案.md`",
            "",
            "## Writing Workflow",
            "",
            "1. Start official chapter creation through `/webnovel-writer:webnovel-chapter [chapter_num]`. If the wrapper is not directly invokable in the current session, mirror its steps exactly; do not substitute a manual one-shot draft.",
            "",
            "2. Resolve the active book with the existing webnovel-writer CLI.",
            "",
            "```bash",
            "python -X utf8 webnovel-writer/scripts/webnovel.py --project-root \"$PWD\" preflight",
            "python -X utf8 webnovel-writer/scripts/webnovel.py --project-root \"$PWD\" where",
            "```",
            "",
            "3. Determine the target chapter from the user request, or use `current_chapter + 1` from `.webnovel/state.json`.",
            "",
            "4. Refresh the runtime contracts if the chapter contract is missing or stale. Do not draft from a previous chapter's contract.",
            "",
            "   For chapters 1-3, the contract/bridge must explicitly load `大纲/黄金三章作战卡.md` and state the current chapter's golden-three role. If the card is missing, stop and rebuild initialization/workflow files before drafting.",
            "",
            "5. Build the No bridge package before drafting.",
            "",
            "```bash",
            "python -X utf8 webnovel-writer/scripts/webnovel.py --project-root \"$PROJECT_ROOT\" ncs-bridge --chapter \"$CHAPTER_NUM\" --recent-chapters 3",
            "```",
            "",
            "6. Before drafting prose, make a short scene-first brief from the bridge package. For chapters 1-3, the brief must name the first-sentence danger, the conflict inside 300 Chinese characters, the memorable scene, the small win, the visible cost, and the next-action hook.",
            "",
            "7. Draft through No/NCS from `.webnovel/tmp/ncs-bridge/` standard files, the chapter control card, and recent chapters.",
            "",
            "8. Put the accepted chapter back into the normal webnovel-writer manuscript path:",
            "",
            "`正文/第NNNN章-标题.md`",
            "",
            "9. Continue with the `/webnovel-writer:webnovel-chapter` wrapped `webnovel-write` Step 3-5 flow exactly: reviewer -> NCS/anti-AI gate -> data-agent artifacts -> chapter-commit -> projection. NCS must not write directly to `.webnovel/state.json` as the source of truth.",
            "",
            "10. Before chapter commit, run the post-chapter update checklist. If the chapter changes any character, skill, item, timeline event, relationship, foreshadowing, or world-state fact, update the corresponding cards/indexes before finalizing.",
            "",
            "11. Reviewer and data-agent artifacts must be regenerated from the current manuscript, not reused from rejected drafts. For fresh-run chapters, write current artifacts with explicit names:",
            "    - `.webnovel/tmp/chNNN_current_review_result.json`",
            "    - `.webnovel/tmp/chNNN_current_fulfillment_result.json`",
            "    - `.webnovel/tmp/chNNN_current_extraction_result.json`",
            "    - `.webnovel/tmp/chNNN_current_disambiguation_result.json`",
            "    Chapter commit may only consume these current artifacts after the user accepts the chapter as official.",
            "",
            "12. Review gate inherits the created `/webnovel-writer:webnovel-chapter` / `webnovel-write` skill flow. It is a rewrite gate, not a cosmetic score. If `blocking_count > 0`, `missed_nodes` is non-empty, disambiguation has pending items, `review_score < 90`, any dimension score is below 85, `AI腔控制 < 88`, `anti_ai_force_check=fail`, chapters 1-3 fail the golden-three role, the opening uses a default passive shock pattern such as `X是被Y弄醒的`, or the reviewer says the chapter has obvious contract/report/prose-template flavor, mark the chapter as `rewrite_required`. Do not commit it, do not continue to the next chapter, and do not use the failed draft as style reference.",
            "",
            "## Drafting Order",
            "",
            "Use this order for every manuscript chapter:",
            "",
            "1. Use `/webnovel-writer:webnovel-chapter [chapter_num]` as the outer chapter flow, with No Webnovel Write as this book's constraint layer.",
            "2. Draft from the bridge/context files and existing chapter contract.",
            "3. Run a light anti-AI/authenticity pass after the draft.",
            "4. The anti-AI pass may only change language, rhythm, dialogue naturalness, and paragraph texture.",
            "5. The anti-AI pass must not change plot facts, character motivation, timeline, power/skill state, item ownership, foreshadowing state, or add new settings.",
            "6. Re-check continuity after the anti-AI pass before committing.",
            "7. Run the created `/webnovel-writer:webnovel-chapter` / `webnovel-write` Step 3-5 sequence; generate or refresh the current review score and current data-agent artifacts before any chapter commit. If old temp files mention facts absent from the current manuscript, treat them as stale and do not use them.",
            "8. If the current review gate fails, stop the chapter flow and rewrite from the scene-first brief. A failed chapter cannot be repaired by only deleting banned words.",
            "",
            "## Post-Chapter Update Requirements",
            "",
            "After the accepted chapter is written, update every affected source of truth. Do not rely on the prose alone.",
            "",
            "Required checks:",
            "",
            "- character cards and character state",
            "- relationships and relationship events",
            "- skill cards, ownership, cooldown/limits, injuries, unlock state, and skill evolution",
            "- item cards, ownership, location, damage, consumption, transfer, loss, or unlock state",
            "- skill/item timeline if any skill or object appears, changes hands, changes state, or creates a future obligation",
            "- story timeline if time anchor, location, event result, state change, or next-chapter pressure changes",
            "- if a new skill or item enters正文 from plan state, create or update its card before finalizing",
            "- outline/timeline/event logs if the chapter advances or changes planned events",
            "- foreshadowing ledger if a clue is planted, paid off, delayed, or invalidated",
            "- chapter summary, memory, index.db, state.json, and projection outputs through the normal webnovel-writer commit flow",
            "",
            "Rules:",
            "",
            "- If nothing changed, explicitly record `no state update needed` in the working notes/check result.",
            "- Never silently change a card to make the new prose fit; if the prose contradicts a card, fix the prose or surface the conflict.",
            "- Anti-AI cleanup must never change state-bearing facts after this check without re-running the check.",
            "",
            "## Anti-AI Taste Rules",
            "",
            "Preserve scene meaning, but reduce:",
            "",
            "- generic emotional summaries",
            "- tidy three-part explanatory prose",
            "- slogans, false depth, and conclusion sentences",
            "- analysis-tone words in narration",
            "- samey dialogue and over-polished speaker rhythm",
            "- decorative blank-line chopping",
            "- overused explanatory forms such as `不是……而是……`, `这意味着……`, `他明白一件事`",
            "- default passive shock openings such as `某人是被某物弄醒的`; this is a rewrite trigger, not a polishing note",
            "",
            "Do not add fake human flavor just to look less AI. Make the scene more concrete, pressured, and voiced.",
            "",
            "## Early Hook Rules",
            "",
            "For chapters 1-30, do not let the chapter become pure archive investigation or rule debate. A clue must quickly turn into pressure, pursuit, betrayal, a visible choice, a concrete win/loss, or an original-canon callback.",
            "",
            "For chapters 1-3, `大纲/黄金三章作战卡.md` is part of the hard chain. Each of the first three chapters must satisfy its role in hook, pressure escalation, relationship progression, first payoff, and next-hook force. Failure means `rewrite_required`.",
            "",
        ]
    )


def _build_codex_project_doc(title: str, genre: str, now: str) -> str:
    return "\n".join(
        [
            "# Codex Project Notes",
            "",
            f"- Project: {title}",
            f"- Genre: {genre}",
            f"- Initialized: {now}",
            "",
            "## Default Writing Rule",
            "",
            "When creating an official chapter in this project, use `/webnovel-writer:webnovel-chapter [chapter_num]` as the outer entry. This is the chapter wrapper that prepares the chapter contract and then runs the normal write chain.",
            "",
            "The local `no-webnovel-write` skill is the project constraint/adaptation layer for this book. It must be used together with the chapter wrapper to keep old-manuscript isolation, No/NCS prose rules, anti-AI taste gates, and fresh-run chapter artifacts in force.",
            "",
            "The project should keep webnovel-writer as the source of truth for cards, timelines, contracts, summaries, memory, index.db, and dashboard state. No/NCS is the prose engine only. It must not bypass chapter contracts or write state-bearing facts without the normal post-chapter update flow.",
            "",
            "`/webnovel-writer:webnovel-chapter` owns chapter-number parsing, contract preparation, NCS bridge, drafting, review, commit, and projection. The local `no-webnovel-write` skill inherits that created `webnovel-chapter` / `webnovel-write` flow, especially Step 3-5: reviewer -> NCS/anti-AI gate -> data-agent artifacts -> chapter-commit -> projection. Do not replace it with manual scoring.",
            "",
            "For chapters 1-3, `大纲/黄金三章作战卡.md` is a required source in the chapter chain. The contract, NCS bridge, scene brief, and review must all check the current chapter's golden-three role; failure is `rewrite_required`.",
            "",
            "For chapters 1-3, use high-stimulation opening gates: first sentence in danger, conflict eruption within 300 Chinese characters, no daily-life/setup opening, one dominant scene, one memorable scene, one visible small win, one visible cost, and one hard next-action hook.",
            "",
            "Opening sentences must avoid the default passive shock pattern such as `X是被Y弄醒的`, `X醒来时发现自己被...`, or equivalent victim-first surprise hooks. If a draft opens this way, rewrite from a concrete object/body/action before review.",
            "",
            "## Review Gate",
            "",
            "- Review is a rewrite gate, not a cosmetic score.",
            "- A chapter must be rewritten if `blocking_count > 0`, `missed_nodes` is non-empty, disambiguation has pending items, `review_score < 90`, any dimension score is below 85, or `AI腔控制 < 88`.",
            "- Chapters 1-3 must also be rewritten if the golden-three role is missing/failed or the opening uses passive shock template prose.",
            "- Failed drafts must not enter `chapter-commit`, must not continue to the next chapter, and must not be used as style reference.",
            "",
        ]
    )


def _inject_volume_rows(template_text: str, target_chapters: int, *, chapters_per_volume: int = 50) -> str:
    """在总纲模板的卷表中只注入首卷行（后续卷由规划完成后写回）。"""
    lines = template_text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("| 卷号"):
            header_idx = i
            break
    if header_idx is None:
        return template_text

    insert_idx = header_idx + 2 if header_idx + 1 < len(lines) else len(lines)
    end = min(chapters_per_volume, target_chapters) if target_chapters > 0 else chapters_per_volume
    rows = [f"| 1 | | 第1-{end}章 | | |"]

    # 避免重复插入（若模板已有数据行）
    existing = {line.strip() for line in lines}
    rows = [r for r in rows if r.strip() not in existing]
    return "\n".join(lines[:insert_idx] + rows + lines[insert_idx:])


def init_project(
    project_dir: str,
    title: str,
    genre: str,
    *,
    protagonist_name: str = "",
    target_words: int = 2_000_000,
    target_chapters: int = 600,
    golden_finger_name: str = "",
    golden_finger_type: str = "",
    golden_finger_style: str = "",
    core_selling_points: str = "",
    protagonist_structure: str = "",
    heroine_config: str = "",
    heroine_names: str = "",
    heroine_role: str = "",
    co_protagonists: str = "",
    co_protagonist_roles: str = "",
    antagonist_tiers: str = "",
    world_scale: str = "",
    factions: str = "",
    power_system_type: str = "",
    social_class: str = "",
    resource_distribution: str = "",
    gf_visibility: str = "",
    gf_irreversible_cost: str = "",
    protagonist_desire: str = "",
    protagonist_flaw: str = "",
    protagonist_archetype: str = "",
    antagonist_level: str = "",
    target_reader: str = "",
    platform: str = "",
    currency_system: str = "",
    currency_exchange: str = "",
    sect_hierarchy: str = "",
    cultivation_chain: str = "",
    cultivation_subtiers: str = "",
) -> None:
    project_path = Path(project_dir).expanduser().resolve()
    if ".claude" in project_path.parts:
        raise SystemExit("Refusing to initialize a project inside .claude. Choose a different directory.")
    genre = _validate_initial_genre_source(genre)
    project_path.mkdir(parents=True, exist_ok=True)

    # 目录结构（同时兼容“卷目录”与后续扩展）
    directories = [
        ".codex/skills/no-webnovel-write",
        ".story-system/chapters",
        ".story-system/commits",
        ".story-system/reviews",
        ".story-system/volumes",
        ".webnovel/backups",
        ".webnovel/archive",
        ".webnovel/summaries",
        "设定集/角色库/主要角色",
        "设定集/角色库/次要角色",
        "设定集/角色库/反派角色",
        "设定集/技能卡",
        "设定集/物品库",
        "设定集/其他设定",
        "大纲",
        "规划",
        "正文",
        "审查报告",
    ]
    for dir_path in directories:
        (project_path / dir_path).mkdir(parents=True, exist_ok=True)

    # state.json（创建或增量补齐）
    state_path = project_path / ".webnovel" / "state.json"
    if state_path.exists():
        try:
            state: Dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    else:
        state = {}

    state = _ensure_state_schema(state)
    created_at = state.get("project_info", {}).get("created_at") or datetime.now().strftime("%Y-%m-%d")

    state["project_info"].update(
        {
            "title": title,
            "genre": genre,
            "created_at": created_at,
            "target_words": int(target_words),
            "target_chapters": int(target_chapters),
            # 下面字段属于“初始化元信息”，不影响运行时脚本
            "golden_finger_name": golden_finger_name,
            "golden_finger_type": golden_finger_type,
            "golden_finger_style": golden_finger_style,
            "core_selling_points": core_selling_points,
            "protagonist_structure": protagonist_structure,
            "heroine_config": heroine_config,
            "heroine_names": heroine_names,
            "heroine_role": heroine_role,
            "co_protagonists": co_protagonists,
            "co_protagonist_roles": co_protagonist_roles,
            "antagonist_tiers": antagonist_tiers,
            "world_scale": world_scale,
            "factions": factions,
            "power_system_type": power_system_type,
            "social_class": social_class,
            "resource_distribution": resource_distribution,
            "gf_visibility": gf_visibility,
            "gf_irreversible_cost": gf_irreversible_cost,
            "target_reader": target_reader,
            "platform": platform,
            "currency_system": currency_system,
            "currency_exchange": currency_exchange,
            "sect_hierarchy": sect_hierarchy,
            "cultivation_chain": cultivation_chain,
            "cultivation_subtiers": cultivation_subtiers,
        }
    )

    if protagonist_name:
        state["protagonist_state"]["name"] = protagonist_name

    gf_type_norm = (golden_finger_type or "").strip()
    if gf_type_norm in {"无", "无金手指", "none"}:
        state["protagonist_state"]["golden_finger"]["name"] = "无金手指"
        state["protagonist_state"]["golden_finger"]["level"] = 0
        state["protagonist_state"]["golden_finger"]["cooldown"] = 0
    elif golden_finger_name:
        state["protagonist_state"]["golden_finger"]["name"] = golden_finger_name

    # 确保 golden_finger 字段存在且可编辑
    if not state["protagonist_state"]["golden_finger"].get("name"):
        state["protagonist_state"]["golden_finger"]["name"] = "未命名金手指"

    state["progress"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # 使用原子化写入（初始化不需要备份旧文件）
    atomic_write_json(state_path, state, use_lock=True, backup=False)

    # 读取内置模板（可选）
    script_dir = Path(__file__).resolve().parent
    templates_dir = script_dir.parent / "templates"
    output_templates_dir = templates_dir / "output"
    genre_key = (genre or "").strip()
    genre_keys = [_normalize_genre_key(k) for k in _split_genre_keys(genre_key)]
    genre_templates = []
    seen = set()
    for key in genre_keys:
        if not key or key in seen:
            continue
        seen.add(key)
        template_text = _read_text_if_exists(templates_dir / "genres" / f"{key}.md")
        if template_text:
            genre_templates.append(template_text.strip())
    genre_template = "\n\n---\n\n".join(genre_templates)
    output_worldview = _read_text_if_exists(output_templates_dir / "设定集-世界观.md")
    output_power = _read_text_if_exists(output_templates_dir / "设定集-力量体系.md")
    output_protagonist = _read_text_if_exists(output_templates_dir / "设定集-主角卡.md")
    output_heroine = _read_text_if_exists(output_templates_dir / "设定集-女主卡.md")
    output_team = _read_text_if_exists(output_templates_dir / "设定集-主角组.md")
    output_outline = _read_text_if_exists(output_templates_dir / "大纲-总纲.md")
    output_antagonist = _read_text_if_exists(output_templates_dir / "设定集-反派设计.md")

    # 基础文件（只在缺失时生成，避免覆盖已有内容）
    now = datetime.now().strftime("%Y-%m-%d")

    _write_text_if_missing(
        project_path / "规划" / "写作流程.md",
        _build_writing_workflow_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / "规划" / "No正文生成提示词.md",
        _build_no_prompt_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / ".webnovel" / "post_chapter_update_checklist.md",
        _build_post_chapter_checklist(title, genre, now),
    )
    _write_text_if_missing(
        project_path / "大纲" / "剧情时间轴.md",
        _build_story_timeline_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / "大纲" / "黄金三章作战卡.md",
        _build_golden_three_card_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / "设定集" / "技能物品时间线.md",
        _build_skill_item_timeline_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / "设定集" / "技能卡" / "技能卡总表.md",
        _build_skill_index_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / "设定集" / "技能卡" / "中后期人物技能更新总表.md",
        _build_mid_late_skill_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / "设定集" / "物品库" / "物品卡总表.md",
        _build_item_index_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / "设定集" / "OOC禁区.md",
        _build_simple_policy_doc(title, genre, now, "ooc"),
    )
    _write_text_if_missing(
        project_path / "设定集" / "平台风格约束.md",
        _build_simple_policy_doc(title, genre, now, "platform"),
    )
    _write_text_if_missing(
        project_path / "设定集" / "改写边界.md",
        _build_simple_policy_doc(title, genre, now, "rewrite"),
    )
    _write_text_if_missing(
        project_path / "设定集" / "原作时间线.md",
        _build_optional_fanfic_doc(title, genre, now, "source_timeline"),
    )
    _write_text_if_missing(
        project_path / "设定集" / "同人分歧点.md",
        _build_optional_fanfic_doc(title, genre, now, "fanfic_divergence"),
    )
    _write_text_if_missing(
        project_path / ".codex" / "skills" / "no-webnovel-write" / "SKILL.md",
        _build_codex_no_skill_doc(title, genre, now),
    )
    _write_text_if_missing(
        project_path / ".codex" / "PROJECT.md",
        _build_codex_project_doc(title, genre, now),
    )

    worldview_content = output_worldview.strip() if output_worldview else ""
    if not worldview_content:
        worldview_content = "\n".join(
            [
                "# 世界观",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "## 一句话世界观",
                "- （用一句话说明世界的核心规则与卖点）",
                "",
                "## 核心规则（设定即物理）",
                "- 规则1：",
                "- 规则2：",
                "- 规则3：",
                "",
                "## 势力与地理（简版）",
                "- 主要势力：",
                "- 关键地点：",
                "",
                "## 参考题材模板（可删/可改）",
                "",
                (genre_template.strip() + "\n") if genre_template else "（未找到对应题材模板，可自行补充）\n",
            ]
        ).rstrip() + "\n"
    else:
        worldview_content = _apply_label_replacements(
            worldview_content,
            {
                "大陆/位面数量": world_scale,
                "核心势力": factions,
                "社会阶层": social_class,
                "资源分配规则": resource_distribution,
                "宗门/组织层级": sect_hierarchy,
                "货币体系": currency_system,
                "兑换规则": currency_exchange,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "世界观.md",
        worldview_content,
    )

    power_content = output_power.strip() if output_power else ""
    if not power_content:
        power_content = "\n".join(
            [
                "# 力量体系",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "## 等级/境界划分",
                "- （列出从弱到强的等级，含突破条件与代价）",
                "",
                "## 技能/招式规则",
                "- 获得方式：",
                "- 成本与副作用：",
                "- 进阶与组合：",
                "",
                "## 禁止事项（防崩坏）",
                "- 未达等级不得使用高阶能力（设定即物理）",
                "- 新增能力必须申报并入库（发明需申报）",
                "",
            ]
        ).rstrip() + "\n"
    else:
        power_content = _apply_label_replacements(
            power_content,
            {
                "体系类型": power_system_type,
                "典型境界链（可选）": cultivation_chain,
                "小境界划分": cultivation_subtiers,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "力量体系.md",
        power_content,
    )

    protagonist_content = output_protagonist.strip() if output_protagonist else ""
    if not protagonist_content:
        protagonist_content = "\n".join(
            [
                "# 主角卡",
                "",
                f"> 主角：{protagonist_name or '（待填写）'}｜项目：{title}｜创建：{now}",
                "",
                "## 三要素",
                f"- 欲望：{protagonist_desire or '（待填写）'}",
                f"- 弱点：{protagonist_flaw or '（待填写）'}",
                f"- 人设类型：{protagonist_archetype or '（待填写）'}",
                "",
                "## 初始状态（开局）",
                "- 身份：",
                "- 资源：",
                "- 约束：",
                "",
                "## 金手指概览",
                f"- 称呼：{golden_finger_name or '（待填写）'}",
                f"- 类型：{golden_finger_type or '（待填写）'}",
                f"- 风格：{golden_finger_style or '（待填写）'}",
                "- 成长曲线：",
                "",
            ]
        ).rstrip() + "\n"
    else:
        protagonist_content = _apply_label_replacements(
            protagonist_content,
            {
                "姓名": protagonist_name,
                "真正渴望（可能不自知）": protagonist_desire,
                "性格缺陷": protagonist_flaw,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "主角卡.md",
        protagonist_content,
    )

    heroine_content = output_heroine.strip() if output_heroine else ""
    if heroine_content and _needs_heroine_card(heroine_config, heroine_names):
        heroine_content = _apply_label_replacements(
            heroine_content,
            {
                "姓名": heroine_names,
                "与主角关系定位（对手/盟友/共谋/牵制）": heroine_role,
            },
        )
        _write_text_if_missing(project_path / "设定集" / "女主卡.md", heroine_content)

    team_content = output_team.strip() if output_team else ""
    if team_content and _needs_protagonist_group(protagonist_structure):
        names = [n.strip() for n in co_protagonists.split(",") if n.strip()] if co_protagonists else []
        roles = [r.strip() for r in co_protagonist_roles.split(",") if r.strip()] if co_protagonist_roles else []
        if names:
            lines = team_content.splitlines()
            new_rows = _render_team_rows(names, roles)
            replaced = False
            out_lines: List[str] = []
            for line in lines:
                if line.strip().startswith("| 主角A"):
                    out_lines.extend(new_rows)
                    replaced = True
                    continue
                if replaced and line.strip().startswith("| 主角"):
                    continue
                out_lines.append(line)
            team_content = "\n".join(out_lines)
        _write_text_if_missing(
            project_path / "设定集" / "主角组.md",
            team_content,
        )

    antagonist_content = output_antagonist.strip() if output_antagonist else ""
    if not antagonist_content:
        antagonist_content = "\n".join(
            [
                "# 反派设计",
                "",
                f"> 项目：{title}｜创建：{now}",
                "",
                f"- 反派等级：{antagonist_level or '（待填写）'}",
                "- 动机：",
                "- 资源/势力：",
                "- 与主角的镜像关系：",
                "- 终局：",
                "",
            ]
        ).rstrip() + "\n"
    else:
        tier_map = _parse_tier_map(antagonist_tiers)
        if tier_map:
            lines = antagonist_content.splitlines()
            out_lines = []
            for line in lines:
                if line.strip().startswith("| 小反派"):
                    name = tier_map.get("小反派", "")
                    out_lines.append(f"| 小反派 | {name} | 前期 | | |")
                    continue
                if line.strip().startswith("| 中反派"):
                    name = tier_map.get("中反派", "")
                    out_lines.append(f"| 中反派 | {name} | 中期 | | |")
                    continue
                if line.strip().startswith("| 大反派"):
                    name = tier_map.get("大反派", "")
                    out_lines.append(f"| 大反派 | {name} | 后期 | | |")
                    continue
                out_lines.append(line)
            antagonist_content = "\n".join(out_lines)
    _write_text_if_missing(project_path / "设定集" / "反派设计.md", antagonist_content)

    outline_content = output_outline.strip() if output_outline else ""
    if outline_content:
        outline_content = _inject_volume_rows(outline_content, int(target_chapters)).rstrip() + "\n"
    else:
        outline_content = _build_master_outline(int(target_chapters))
    _write_text_if_missing(project_path / "大纲" / "总纲.md", outline_content)

    # 生成环境变量模板（不写入真实密钥）
    _write_text_if_missing(
        project_path / ".env.example",
        "\n".join(
            [
                "# Webnovel Writer 配置示例（复制为 .env 后填写）",
                "# 注意：请勿将包含真实 API_KEY 的 .env 提交到版本库。",
                "",
                "# Embedding",
                "EMBED_BASE_URL=https://api-inference.modelscope.cn/v1",
                "EMBED_MODEL=Qwen/Qwen3-Embedding-8B",
                "EMBED_API_KEY=",
                "",
                "# Rerank",
                "RERANK_BASE_URL=https://api.jina.ai/v1",
                "RERANK_MODEL=jina-reranker-v3",
                "RERANK_API_KEY=",
                "",
            ]
        )
        + "\n",
    )

    # Git 初始化（仅当项目目录内尚无 .git 且 Git 可用）
    git_dir = project_path / ".git"
    if not git_dir.exists():
        if not is_git_available():
            print("\n⚠️  Git 不可用，跳过版本控制初始化")
            print("💡 如需启用 Git 版本控制，请安装 Git: https://git-scm.com/")
        else:
            print("\nInitializing Git repository...")
            try:
                subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True, text=True)

                gitignore_file = project_path / ".gitignore"
                if not gitignore_file.exists():
                    gitignore_file.write_text(
                        """# Python
__pycache__/
*.py[cod]
*.so

# Env (keep .env.example)
.env
.env.*
!.env.example

# Temporary files
*.tmp
*.bak
.DS_Store

# IDE
.vscode/
.idea/

# Don't ignore .webnovel (we need to track state.json)
# But ignore cache files
.webnovel/context_cache.json
.webnovel/*.lock
.webnovel/*.bak
""",
                        encoding="utf-8",
                    )

                subprocess.run(["git", "add", "."], cwd=project_path, check=True, capture_output=True)
                # 安全修复：清理 title 防止命令注入
                safe_title = sanitize_commit_message(title)
                subprocess.run(
                    ["git", "commit", "-m", f"初始化网文项目：{safe_title}"],
                    cwd=project_path,
                    check=True,
                    capture_output=True,
                )
                print("Git initialized.")
            except subprocess.CalledProcessError as e:
                print(f"Git init failed (non-fatal): {e}")

    # 记录工作区默认项目指针（非阻断）
    try:
        pointer_file = write_current_project_pointer(project_path)
        if pointer_file is not None:
            print(f"Default project pointer updated: {pointer_file}")
    except Exception as e:
        print(f"Default project pointer update failed (non-fatal): {e}")

    print(f"\nProject initialized at: {project_path}")
    print("Key files:")
    print(" - .webnovel/state.json")
    print(" - 设定集/世界观.md")
    print(" - 设定集/力量体系.md")
    print(" - 设定集/主角卡.md")
    print(" - 设定集/金手指设计.md")
    print(" - 设定集/技能物品时间线.md")
    print(" - 设定集/技能卡/技能卡总表.md")
    print(" - 设定集/物品库/物品卡总表.md")
    print(" - 大纲/总纲.md")
    print(" - 大纲/爽点规划.md")
    print(" - 大纲/剧情时间轴.md")
    print(" - 大纲/黄金三章作战卡.md")
    print(" - 规划/写作流程.md")
    print(" - 规划/No正文生成提示词.md")
    print(" - .webnovel/post_chapter_update_checklist.md")
    print(" - .codex/skills/no-webnovel-write/SKILL.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="网文项目初始化脚本（生成项目结构 + state.json + 基础模板）")
    parser.add_argument("project_dir", help="项目目录（建议 ./webnovel-project）")
    parser.add_argument("title", help="小说标题")
    parser.add_argument(
        "genre",
        help="题材类型（可用“+”组合，如：都市脑洞+规则怪谈；示例：修仙/系统流/都市异能/古言/现实题材）",
    )

    parser.add_argument("--protagonist-name", default="", help="主角姓名")
    parser.add_argument("--target-words", type=int, default=2_000_000, help="目标总字数（默认 2000000）")
    parser.add_argument("--target-chapters", type=int, default=600, help="目标总章节数（默认 600）")

    parser.add_argument("--golden-finger-name", default="", help="金手指称呼/系统名（建议读者可见的代号）")
    parser.add_argument("--golden-finger-type", default="", help="金手指类型（如 系统流/鉴定流/签到流）")
    parser.add_argument("--golden-finger-style", default="", help="金手指风格（如 冷漠工具型/毒舌吐槽型）")
    parser.add_argument("--core-selling-points", default="", help="核心卖点（逗号分隔）")
    parser.add_argument("--protagonist-structure", default="", help="主角结构（单主角/多主角）")
    parser.add_argument("--heroine-config", default="", help="女主配置（无女主/单女主/多女主）")
    parser.add_argument("--heroine-names", default="", help="女主姓名（多个用逗号分隔）")
    parser.add_argument("--heroine-role", default="", help="女主定位（事业线/情感线/对抗线）")
    parser.add_argument("--co-protagonists", default="", help="多主角姓名（逗号分隔）")
    parser.add_argument("--co-protagonist-roles", default="", help="多主角定位（逗号分隔）")
    parser.add_argument("--antagonist-tiers", default="", help="反派分层（如 小反派:张三;中反派:李四;大反派:王五）")
    parser.add_argument("--world-scale", default="", help="世界规模")
    parser.add_argument("--factions", default="", help="势力格局/核心势力")
    parser.add_argument("--power-system-type", default="", help="力量体系类型")
    parser.add_argument("--social-class", default="", help="社会阶层")
    parser.add_argument("--resource-distribution", default="", help="资源分配")
    parser.add_argument("--gf-visibility", default="", help="金手指可见度（明牌/半明牌/暗牌）")
    parser.add_argument("--gf-irreversible-cost", default="", help="金手指不可逆代价")
    parser.add_argument("--currency-system", default="", help="货币体系")
    parser.add_argument("--currency-exchange", default="", help="货币兑换/面值规则")
    parser.add_argument("--sect-hierarchy", default="", help="宗门/组织层级")
    parser.add_argument("--cultivation-chain", default="", help="典型境界链")
    parser.add_argument("--cultivation-subtiers", default="", help="小境界划分（初/中/后/巅 等）")

    # 深度模式可选参数（用于预填模板）
    parser.add_argument("--protagonist-desire", default="", help="主角核心欲望（深度模式）")
    parser.add_argument("--protagonist-flaw", default="", help="主角性格弱点（深度模式）")
    parser.add_argument("--protagonist-archetype", default="", help="主角人设类型（深度模式）")
    parser.add_argument("--antagonist-level", default="", help="反派等级（深度模式）")
    parser.add_argument("--target-reader", default="", help="目标读者（深度模式）")
    parser.add_argument("--platform", default="", help="发布平台（深度模式）")

    args = parser.parse_args()

    init_project(
        args.project_dir,
        args.title,
        args.genre,
        protagonist_name=args.protagonist_name,
        target_words=args.target_words,
        target_chapters=args.target_chapters,
        golden_finger_name=args.golden_finger_name,
        golden_finger_type=args.golden_finger_type,
        golden_finger_style=args.golden_finger_style,
        core_selling_points=args.core_selling_points,
        protagonist_structure=args.protagonist_structure,
        heroine_config=args.heroine_config,
        heroine_names=args.heroine_names,
        heroine_role=args.heroine_role,
        co_protagonists=args.co_protagonists,
        co_protagonist_roles=args.co_protagonist_roles,
        antagonist_tiers=args.antagonist_tiers,
        world_scale=args.world_scale,
        factions=args.factions,
        power_system_type=args.power_system_type,
        social_class=args.social_class,
        resource_distribution=args.resource_distribution,
        gf_visibility=args.gf_visibility,
        gf_irreversible_cost=args.gf_irreversible_cost,
        protagonist_desire=args.protagonist_desire,
        protagonist_flaw=args.protagonist_flaw,
        protagonist_archetype=args.protagonist_archetype,
        antagonist_level=args.antagonist_level,
        target_reader=args.target_reader,
        platform=args.platform,
        currency_system=args.currency_system,
        currency_exchange=args.currency_exchange,
        sect_hierarchy=args.sect_hierarchy,
        cultivation_chain=args.cultivation_chain,
        cultivation_subtiers=args.cultivation_subtiers,
    )


if __name__ == "__main__":
    main()
