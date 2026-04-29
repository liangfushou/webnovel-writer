#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def test_ncs_bridge_exports_standard_files(tmp_path):
    _ensure_scripts_on_path()
    import ncs_bridge

    project_root = tmp_path / "book"
    (project_root / ".webnovel" / "summaries").mkdir(parents=True)
    (project_root / ".webnovel" / "knowledge").mkdir(parents=True)
    (project_root / ".story-system" / "chapters").mkdir(parents=True)
    (project_root / ".story-system" / "reviews").mkdir(parents=True)
    (project_root / ".story-system" / "volumes").mkdir(parents=True)
    (project_root / "设定集").mkdir(parents=True)
    (project_root / "设定集" / "技能卡").mkdir(parents=True)
    (project_root / "大纲").mkdir(parents=True)
    (project_root / "正文").mkdir(parents=True)

    (project_root / ".webnovel" / "state.json").write_text(
        json.dumps(
            {
                "project_info": {
                    "title": "测试书",
                    "genre": "规则怪谈",
                    "target_words": 1000000,
                    "target_chapters": 400,
                    "core_selling_points": "规则破解, 代价交换",
                },
                "progress": {
                    "current_chapter": 2,
                    "total_words": 4200,
                    "volumes_planned": [{"volume": 1, "chapters_range": "1-50"}],
                },
                "protagonist_state": {"name": "谢临渊", "location": {"current": "谢家村"}},
                "plot_threads": {"foreshadowing": [{"content": "棺中替身"}]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_root / "设定集" / "主角卡.md").write_text("# 主角卡\n\n- 姓名：谢临渊\n", encoding="utf-8")
    (project_root / "设定集" / "反派设计.md").write_text("# 反派设计\n\n- 棺中替身\n", encoding="utf-8")
    (project_root / "设定集" / "世界观.md").write_text("# 世界观\n\n谢家村守棺会。\n", encoding="utf-8")
    (project_root / "设定集" / "力量体系.md").write_text("# 力量体系\n\n识禁。\n", encoding="utf-8")
    (project_root / "大纲" / "总纲.md").write_text("# 总纲\n\n主线：活人资格。\n", encoding="utf-8")
    (project_root / "大纲" / "第1卷-详细大纲.md").write_text("## 第3章\n目标：离开灵堂。\n", encoding="utf-8")
    (project_root / "大纲" / "第1卷-时间线.md").write_text("末世第1天：谢临渊守灵后必须在天亮前离村。\n", encoding="utf-8")
    (project_root / "大纲" / "第1卷-节拍表.md").write_text("午夜回钩：纸人第二次敲门。\n", encoding="utf-8")
    (project_root / ".webnovel" / "summaries" / "ch0002.md").write_text("第二章摘要。", encoding="utf-8")
    (project_root / ".webnovel" / "knowledge" / "谢临渊.md").write_text("当前状态：失温，仍在谢家村。\n", encoding="utf-8")
    (project_root / "正文" / "第0002章-守灵.md").write_text("上一章正文。", encoding="utf-8")
    conn = sqlite3.connect(str(project_root / ".webnovel" / "index.db"))
    conn.execute(
        """
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            canonical_name TEXT,
            type TEXT,
            tier TEXT,
            current_json TEXT,
            last_appearance INTEGER,
            is_protagonist INTEGER,
            is_archived INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE state_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT,
            field TEXT,
            old_value TEXT,
            new_value TEXT,
            chapter INTEGER
        )
        """
    )
    conn.execute(
        "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("xie_linyuan", "谢临渊", "角色", "核心", json.dumps({"location": "谢家村"}, ensure_ascii=False), 2, 1, 0),
    )
    conn.execute(
        "INSERT INTO state_changes (entity_id, field, old_value, new_value, chapter) VALUES (?, ?, ?, ?, ?)",
        ("xie_linyuan", "状态", "正常", "失温", 2),
    )
    conn.commit()
    conn.close()
    (project_root / ".story-system" / "MASTER_SETTING.json").write_text(
        json.dumps({"master_constraints": {"core_tone": "冷硬"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_root / ".story-system" / "chapters" / "chapter_003.json").write_text(
        json.dumps({"meta": {"chapter": 3}, "override_allowed": {"chapter_focus": "离开灵堂"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_root / ".story-system" / "reviews" / "chapter_003.review.json").write_text(
        json.dumps({"forbidden_in_chapter": ["不能无代价破禁"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest = ncs_bridge.build_bridge(project_root, chapter=3, output_dir=None, recent_chapters=1)
    bridge_dir = Path(manifest["bridge_dir"])

    assert (bridge_dir / "00-project-overview.md").is_file()
    assert (bridge_dir / "03-cast-bible.md").read_text(encoding="utf-8").find("谢临渊") >= 0
    roadmap = (bridge_dir / "07-chapter-roadmap.md").read_text(encoding="utf-8")
    assert "离开灵堂" in roadmap
    assert "末世第1天" in roadmap
    assert "午夜回钩" in roadmap
    dynamic_state = (bridge_dir / "08-dynamic-state.md").read_text(encoding="utf-8")
    assert "资料库快照" in dynamic_state
    assert "当前状态：失温" in dynamic_state
    control_card = (bridge_dir / "control-cards" / "03-control-card.md").read_text(encoding="utf-8")
    assert "离开灵堂" in control_card
    assert "本章窄入口" in control_card
    assert "不主动调用中后期计划态内容" in control_card
    assert "不能无代价破禁" in control_card
    assert (bridge_dir / "chapters" / "2-守灵.md").is_file()
    assert manifest["chapter"] == 3


def test_ncs_bridge_accepts_fanfic_contract_and_root_index_db(tmp_path):
    _ensure_scripts_on_path()
    import ncs_bridge

    project_root = tmp_path / "naruto_fanfic"
    (project_root / ".webnovel" / "summaries").mkdir(parents=True)
    (project_root / ".story-system" / "chapters").mkdir(parents=True)
    (project_root / ".story-system" / "volumes").mkdir(parents=True)
    (project_root / "设定集").mkdir(parents=True)
    (project_root / "设定集" / "技能卡").mkdir(parents=True)
    (project_root / "大纲").mkdir(parents=True)
    (project_root / "正文").mkdir(parents=True)

    (project_root / ".webnovel" / "state.json").write_text(
        json.dumps(
            {
                "book_id": "naruto_fanfic_blood_mist_judge_001",
                "book_title": "火影：血雾里走出的判忍",
                "current_volume": 1,
                "current_chapter": 0,
                "last_completed_chapter": 0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_root / ".story-system" / "MASTER_SETTING.json").write_text(
        json.dumps({"title": "火影：血雾里走出的判忍", "genre": ["火影同人"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_root / ".story-system" / "chapters" / "chapter_001_contract.json").write_text(
        json.dumps({"chapter_goal": "雾原朔登场，看见白的死劫。", "must_keep": ["卡卡西不能降智"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_root / "大纲" / "总纲.md").write_text("主线：救白和再不斩，清算血雾旧账。", encoding="utf-8")
    (project_root / "大纲" / "同人爽点模型.md").write_text("爽点：熟悉遗憾被改写。", encoding="utf-8")
    (project_root / "大纲" / "第1卷-详细大纲.md").write_text("## 第1章：桥上的白线\n目标：看见白的死劫。\n", encoding="utf-8")
    (project_root / "大纲" / "第1卷-时间线.md").write_text("波之国大桥：白准备替再不斩挡下雷切。\n", encoding="utf-8")
    (project_root / "设定集" / "主角卡.md").write_text("雾原朔：土著原创主角，死劫之眼。", encoding="utf-8")
    (project_root / "设定集" / "世界观.md").write_text("火影忍者世界。", encoding="utf-8")
    (project_root / "设定集" / "力量体系.md").write_text("查克拉、忍术、血继限界。", encoding="utf-8")
    (project_root / "设定集" / "技能物品时间线.md").write_text(
        "死劫之眼：第1章首次出现。斩首大刀：当前持有人桃地再不斩。",
        encoding="utf-8",
    )
    (project_root / "设定集" / "原作设定卡.md").write_text("白拥有冰遁血继限界。", encoding="utf-8")
    (project_root / "设定集" / "OOC禁区.md").write_text("卡卡西不能降智。白不能开局背叛再不斩。", encoding="utf-8")
    (project_root / "设定集" / "改写边界.md").write_text("第一卷不能明牌黑绝。", encoding="utf-8")
    (project_root / "设定集" / "技能卡" / "雾原朔-死劫之眼.md").write_text(
        "死劫之眼：只能看见近期死亡节点，不能看见完整剧情。",
        encoding="utf-8",
    )
    (project_root / "设定集" / "物品库").mkdir(parents=True)
    (project_root / "设定集" / "物品库" / "斩首大刀.md").write_text(
        "斩首大刀：当前持有人桃地再不斩，第一卷不能轻易换主。",
        encoding="utf-8",
    )

    conn = sqlite3.connect(str(project_root / "index.db"))
    conn.execute("CREATE TABLE entities (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, description TEXT, source_file TEXT)")
    conn.execute("CREATE TABLE continuity_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, rule_name TEXT, rule_text TEXT, priority INTEGER)")
    conn.execute("INSERT INTO entities (name, type, description, source_file) VALUES (?, ?, ?, ?)", ("白", "原作角色", "冰遁血继少年", "设定集/原作设定卡.md"))
    conn.execute("INSERT INTO continuity_rules (rule_name, rule_text, priority) VALUES (?, ?, ?)", ("OOC", "卡卡西不能降智", 10))
    conn.commit()
    conn.close()

    manifest = ncs_bridge.build_bridge(project_root, chapter=1, output_dir=None, recent_chapters=1)
    bridge_dir = Path(manifest["bridge_dir"])

    overview = (bridge_dir / "00-project-overview.md").read_text(encoding="utf-8")
    world = (bridge_dir / "02-worldbuilding.md").read_text(encoding="utf-8")
    roadmap = (bridge_dir / "07-chapter-roadmap.md").read_text(encoding="utf-8")
    dynamic_state = (bridge_dir / "08-dynamic-state.md").read_text(encoding="utf-8")
    control_card = (bridge_dir / "control-cards" / "01-control-card.md").read_text(encoding="utf-8")

    assert "火影：血雾里走出的判忍" in overview
    assert "熟悉遗憾被改写" in overview
    assert "技能卡/招式库" in world
    assert "只能看见近期死亡节点" in world
    assert "技能物品时间线" in world
    assert "第1章首次出现" in world
    assert "物品卡/道具库" in world
    assert "第一卷不能轻易换主" in world
    assert "白不能开局背叛再不斩" in world
    assert "波之国大桥" in roadmap
    assert "卡卡西不能降智" in control_card
    assert "看见白的死劫" in control_card
    assert "不主动调用中后期计划态内容" in control_card
    assert "冰遁血继少年" in dynamic_state
    assert manifest["volume"] == 1


def test_ncs_bridge_merges_root_index_when_standard_index_is_empty(tmp_path):
    _ensure_scripts_on_path()
    import ncs_bridge

    project_root = tmp_path / "naruto_fanfic"
    (project_root / ".webnovel").mkdir(parents=True)
    (project_root / ".story-system" / "chapters").mkdir(parents=True)
    (project_root / ".story-system" / "volumes").mkdir(parents=True)
    (project_root / "设定集").mkdir(parents=True)
    (project_root / "大纲").mkdir(parents=True)
    (project_root / "正文").mkdir(parents=True)

    (project_root / ".webnovel" / "state.json").write_text(
        json.dumps({"book_title": "火影：血雾里走出的判忍", "current_chapter": 0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_root / ".story-system" / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")
    (project_root / ".story-system" / "chapters" / "chapter_001_contract.json").write_text(
        json.dumps({"chapter_goal": "看见白的死劫"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_root / "大纲" / "第1卷-详细大纲.md").write_text("## 第1章：桥上的白线\n目标：救白。", encoding="utf-8")

    standard = sqlite3.connect(str(project_root / ".webnovel" / "index.db"))
    standard.execute(
        """
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            canonical_name TEXT,
            type TEXT,
            tier TEXT,
            current_json TEXT,
            last_appearance INTEGER,
            is_protagonist INTEGER,
            is_archived INTEGER
        )
        """
    )
    standard.commit()
    standard.close()

    legacy = sqlite3.connect(str(project_root / "index.db"))
    legacy.execute("CREATE TABLE entities (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, description TEXT, source_file TEXT)")
    legacy.execute("INSERT INTO entities (name, type, description, source_file) VALUES (?, ?, ?, ?)", ("白", "原作角色", "冰遁血继少年", "设定集/原作设定卡.md"))
    legacy.commit()
    legacy.close()

    manifest = ncs_bridge.build_bridge(project_root, chapter=1, output_dir=None, recent_chapters=1)
    dynamic_state = (Path(manifest["bridge_dir"]) / "08-dynamic-state.md").read_text(encoding="utf-8")

    assert "冰遁血继少年" in dynamic_state
    assert "legacy_root_index" in dynamic_state
