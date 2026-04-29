#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.memory.store import ScratchpadManager
from data_modules.index_projection_writer import IndexProjectionWriter
from data_modules.memory_projection_writer import MemoryProjectionWriter
from data_modules.state_projection_writer import StateProjectionWriter
from data_modules.summary_projection_writer import SummaryProjectionWriter


def test_state_projection_writer_handles_rejected_commit(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    result = writer.apply({"meta": {"status": "rejected", "chapter": 3}, "state_deltas": []})
    assert result["applied"] is True
    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["progress"]["chapter_status"]["3"] == "chapter_rejected"


def test_state_projection_writer_applies_accepted_commit(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "正文").mkdir(parents=True, exist_ok=True)
    (tmp_path / "正文" / "第0003章.md").write_text("# 第3章\n这是正文内容", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "state_deltas": [{"entity_id": "x", "field": "realm", "new": "斗者"}],
        }
    )
    assert result["applied"] is True
    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert payload["entity_state"]["x"]["realm"] == "斗者"
    assert payload["progress"]["chapter_status"]["3"] == "chapter_committed"
    assert payload["progress"]["current_chapter"] == 3
    assert payload["current_chapter"] == 3
    assert payload["last_completed_chapter"] == 3
    assert payload["progress"]["total_words"] == len("这是正文内容")


def test_state_projection_writer_recomputes_total_words_from_committed_chapters(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / "正文").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(
            {
                "progress": {
                    "current_chapter": 1,
                    "total_words": 999,
                    "chapter_status": {"1": "chapter_committed", "2": "chapter_drafted"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "正文" / "第0001章.md").write_text("# 第1章\n甲乙丙丁", encoding="utf-8")
    (tmp_path / "正文" / "第0003章.md").write_text("# 第3章\n天地玄黄", encoding="utf-8")

    writer = StateProjectionWriter(tmp_path)
    writer.apply({"meta": {"status": "accepted", "chapter": 3}, "state_deltas": []})

    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert payload["progress"]["current_chapter"] == 3
    assert payload["progress"]["chapter_status"]["3"] == "chapter_committed"
    assert payload["progress"]["total_words"] == len("甲乙丙丁") + len("天地玄黄")


def test_state_projection_writer_derives_state_delta_from_event(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "state_deltas": [],
            "accepted_events": [
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "power_breakthrough",
                    "subject": "xiaoyan",
                    "payload": {"from": "斗者", "to": "斗师"},
                }
            ],
        }
    )

    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert result["applied"] is True
    assert payload["entity_state"]["xiaoyan"]["realm"] == "斗师"


def test_state_projection_writer_projects_foreshadowing_from_events_and_summary(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

    writer = StateProjectionWriter(tmp_path)
    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "state_deltas": [],
            "accepted_events": [
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "open_loop_created",
                    "subject": "三年之约",
                    "payload": {"content": "三年之约", "tier": "核心", "target_chapter": 9},
                },
                {
                    "event_id": "evt-002",
                    "chapter": 5,
                    "event_type": "promise_paid_off",
                    "subject": "旧债",
                    "payload": {"content": "旧债", "tier": "支线"},
                },
            ],
            "summary_text": "## 剧情摘要\n主角暂时隐忍。\n\n## 伏笔\n- [支线] 纸人会记住气味\n\n## 承接点\n- 下章回收",
        }
    )

    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    items = payload["plot_threads"]["foreshadowing"]
    by_content = {item["content"]: item for item in items}
    assert result["applied"] is True
    assert by_content["三年之约"]["status"] == "未回收"
    assert by_content["三年之约"]["target_chapter"] == 9
    assert by_content["旧债"]["status"] == "已回收"
    assert by_content["旧债"]["resolved_chapter"] == 5
    assert by_content["纸人会记住气味"]["planted_chapter"] == 3


def test_accepted_commit_updates_state_json_end_to_end(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

    service = ChapterCommitService(tmp_path)
    commit_payload = service.build_commit(
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": ["发现陷阱"], "covered_nodes": ["发现陷阱"], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [{"entity_id": "x", "field": "realm", "new": "斗者"}], "entity_deltas": [], "accepted_events": []},
    )

    StateProjectionWriter(tmp_path).apply(commit_payload)
    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert payload["entity_state"]["x"]["realm"] == "斗者"


def test_index_projection_writer_applies_entity_delta(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "entity_deltas": [
                {
                    "entity_id": "xiaoyan",
                    "canonical_name": "萧炎",
                    "type": "角色",
                    "current": {"realm": "斗者"},
                    "chapter": 3,
                }
            ],
        }
    )

    entity = IndexManager(cfg).get_entity("xiaoyan")
    assert result["applied"] is True
    assert entity["canonical_name"] == "萧炎"
    assert entity["current_json"]["realm"] == "斗者"


def test_index_projection_writer_flattens_payload_and_related_models(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (tmp_path / "正文").mkdir(parents=True, exist_ok=True)
    (tmp_path / "正文" / "第0003章-活人守灵.md").write_text("# 第3章：活人守灵\n谢临渊看见纸棺。", encoding="utf-8")
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "entity_deltas": [
                {
                    "entity_id": "xie_linyuan",
                    "payload": {
                        "name": "谢临渊",
                        "type": "人物",
                        "tier": "主角",
                        "aliases": ["临渊"],
                        "attributes": {"realm": "沾阴相"},
                        "relationships": [
                            {"target": "xie_mother", "relation": "母子", "description": "相依为命"}
                        ],
                    },
                }
            ],
            "state_deltas": [
                {"entity_id": "xie_linyuan", "field": "生存状态", "old": "濒死", "new": "活人"}
            ],
            "review_result": {
                "review_score": 88,
                "审查维度": {"节奏": {"score": 90}},
                "问题清单": [{"severity": "low", "问题": "个别句子稍长"}],
                "总结": "整体良好",
            },
            "summary_text": "---\nhook_type: 生死钩\nhook_strength: strong\nlocation: [\"谢家村\"]\n---\n## 剧情摘要\n谢临渊被迫守灵。",
            "accepted_events": [
                {
                    "event_id": "evt-010",
                    "chapter": 3,
                    "event_type": "relationship_changed",
                    "subject": "xie_linyuan",
                    "payload": {
                        "to_entity": "paper_coffin_001",
                        "relationship_type": "对抗",
                        "description": "开始试探纸棺",
                    },
                }
            ],
        }
    )

    manager = IndexManager(cfg)
    entity = manager.get_entity("xie_linyuan")
    alias = manager.resolve_alias("临渊")
    relationships = manager.get_relationship_between("xie_linyuan", "xie_mother")
    events = manager.get_relationship_events(limit=20)
    changes = manager.get_state_changes(entity_id="xie_linyuan", limit=20)
    chapters = manager.list_chapters(limit=10, offset=0)
    trend = manager.chapter_trend(limit=10, offset=0)

    assert result["applied"] is True
    assert entity["canonical_name"] == "谢临渊"
    assert entity["entity_type"] == "角色"
    assert entity["current_json"]["realm"] == "沾阴相"
    assert alias["canonical_id"] == "xie_linyuan"
    assert any(item["type"] == "母子" for item in relationships)
    assert any(item["type"] == "对抗" for item in events)
    assert changes[0]["field"] == "生存状态"
    assert chapters[0]["title"] == "活人守灵"
    assert chapters[0]["location"] == "谢家村"
    assert trend[0]["hook_strength"] == "strong"
    assert trend[0]["review_score"] == 88


def test_index_projection_writer_derives_relationship_from_event(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "entity_deltas": [],
            "accepted_events": [
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "relationship_changed",
                    "subject": "xiaoyan",
                    "payload": {
                        "to_entity": "yaolao",
                        "relationship_type": "师徒",
                        "description": "关系正式确立",
                    },
                }
            ],
        }
    )

    rels = IndexManager(cfg).get_relationship_between("xiaoyan", "yaolao")
    assert result["applied"] is True
    assert rels[0]["type"] == "师徒"


def test_index_projection_writer_derives_artifact_entity_from_event(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "entity_deltas": [],
            "accepted_events": [
                {
                    "event_id": "evt-002",
                    "chapter": 3,
                    "event_type": "artifact_obtained",
                    "subject": "黑戒",
                    "payload": {
                        "artifact_id": "black_ring",
                        "name": "黑戒",
                        "owner": "xiaoyan",
                    },
                }
            ],
        }
    )

    entity = IndexManager(cfg).get_entity("black_ring")
    assert result["applied"] is True
    assert entity["canonical_name"] == "黑戒"
    assert entity["current_json"]["holder"] == "xiaoyan"


def test_summary_projection_writer_writes_summary_markdown(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = SummaryProjectionWriter(tmp_path)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "summary_text": "本章主角发现陷阱并决定隐忍。",
        }
    )

    summary_path = tmp_path / ".webnovel" / "summaries" / "ch0003.md"
    assert result["applied"] is True
    assert summary_path.is_file()
    assert "剧情摘要" in summary_path.read_text(encoding="utf-8")


def test_memory_projection_writer_maps_commit_into_scratchpad(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = MemoryProjectionWriter(tmp_path)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "state_deltas": [
                {"entity_id": "xiaoyan", "field": "realm", "old": "斗者", "new": "斗师"}
            ],
            "entity_deltas": [],
            "accepted_events": [],
        }
    )

    store = ScratchpadManager(cfg)
    chars = store.query(category="character_state", status="active")
    assert result["applied"] is True
    assert any(x.subject == "xiaoyan" and x.field == "realm" for x in chars)


def test_memory_projection_writer_maps_open_loop_event_into_scratchpad(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = MemoryProjectionWriter(tmp_path)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 3},
            "state_deltas": [],
            "entity_deltas": [],
            "accepted_events": [
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "open_loop_created",
                    "subject": "三年之约",
                    "payload": {"content": "三年之约"},
                }
            ],
        }
    )

    store = ScratchpadManager(cfg)
    loops = store.query(category="open_loop", status="active")
    assert result["applied"] is True
    assert any("三年之约" in x.subject for x in loops)
