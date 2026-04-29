"""
Webnovel Dashboard - FastAPI 主应用

提供 Dashboard 只读查询接口，以及显式触发的导出/发布辅助接口。
所有文件读取经过 path_guard 防穿越校验。
"""

import asyncio
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .path_guard import safe_resolve
from .watcher import FileWatcher

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_project_root: Path | None = None
_watcher = FileWatcher()

STATIC_DIR = Path(__file__).parent / "frontend" / "dist"


def _get_project_root() -> Path:
    if _project_root is None:
        raise HTTPException(status_code=500, detail="项目根目录未配置")
    return _project_root


def _webnovel_dir() -> Path:
    return _get_project_root() / ".webnovel"


def _story_system_dir() -> Path:
    return _get_project_root() / ".story-system"


def _build_story_runtime_health_report(project_root: Path) -> dict:
    from data_modules.story_runtime_health import build_story_runtime_health

    return build_story_runtime_health(project_root)


def _ensure_scripts_dir_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    scripts_entry = str(scripts_dir)
    if scripts_entry not in sys.path:
        sys.path.insert(0, scripts_entry)


def _load_state_payload(*, required: bool = False) -> dict:
    state_path = _webnovel_dir() / "state.json"
    if not state_path.is_file():
        if required:
            raise HTTPException(404, "state.json 不存在")
        return {}

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"state.json 读取失败: {exc}") from exc

    return _normalize_state_payload(payload) if isinstance(payload, dict) else {}


def _infer_volumes_planned(project_root: Path) -> list[dict]:
    outline_dir = project_root / "大纲"
    if not outline_dir.is_dir():
        return []

    planned = []
    for path in sorted(outline_dir.glob("第*卷*详细大纲*.md")):
        volume_match = re.search(r"第(\d+)卷", path.name)
        if not volume_match:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        chapter_nums = [
            int(item)
            for item in re.findall(r"^##+\s*第\s*(\d+)\s*章", text, flags=re.MULTILINE)
        ]
        if not chapter_nums:
            continue
        volume_num = int(volume_match.group(1))
        title_match = re.search(
            r"^#\s*第\s*\d+\s*卷(?:详细大纲)?\s*[：:-]\s*(.+?)\s*$",
            text,
            flags=re.MULTILINE,
        )
        title = f"第{volume_num}卷"
        if title_match:
            title = f"第{volume_num}卷：{title_match.group(1).strip()}"
        planned.append(
            {
                "volume": volume_num,
                "chapters_range": f"{min(chapter_nums)}-{max(chapter_nums)}",
                "title": title,
            }
        )
    planned.sort(key=lambda item: int(item.get("volume") or 0))
    return planned


def _parse_chapter_range_end(chapter_range: object) -> int:
    return _parse_chapter_range_bounds(chapter_range)[1]


def _parse_chapter_range_bounds(chapter_range: object) -> tuple[int, int]:
    raw = str(chapter_range or "").strip()
    match = re.search(r"(\d+)\s*[-~—–至到]\s*(\d+)", raw)
    if not match:
        return (0, 0)
    try:
        return int(match.group(1)), int(match.group(2))
    except ValueError:
        return (0, 0)


def _infer_target_chapters(volumes_planned: list[dict]) -> int:
    return max((_parse_chapter_range_end(item.get("chapters_range")) for item in volumes_planned), default=0)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _normalize_state_payload(payload: dict) -> dict:
    """Add standard dashboard fields without discarding legacy No/NCS state keys."""
    normalized = dict(payload)
    project_root = _get_project_root()
    volumes_planned = _infer_volumes_planned(project_root)
    target_chapters = (
        _safe_int(normalized.get("target_chapters"))
        or _infer_target_chapters(volumes_planned)
    )

    if not isinstance(normalized.get("project_info"), dict):
        project_info = dict(normalized.get("project") or {})
        project_info.setdefault("title", normalized.get("book_title") or normalized.get("title") or "")
        project_info.setdefault("book_id", normalized.get("book_id") or "")
        project_info.setdefault("genre", normalized.get("genre") or normalized.get("book_genre") or "")
        if not project_info.get("genre"):
            master_path = _story_system_dir() / "MASTER_SETTING.json"
            try:
                master = json.loads(master_path.read_text(encoding="utf-8")) if master_path.is_file() else {}
            except (OSError, json.JSONDecodeError):
                master = {}
            raw_genre = (master.get("route") or {}).get("primary_genre") or master.get("genre") or ""
            project_info["genre"] = "、".join(raw_genre) if isinstance(raw_genre, list) else str(raw_genre)
        if "total_planned_volumes" in normalized:
            project_info.setdefault("target_volumes", normalized.get("total_planned_volumes"))
        normalized["project_info"] = project_info
    else:
        project_info = dict(normalized.get("project_info") or {})
        normalized["project_info"] = project_info

    project_info.setdefault("target_words", normalized.get("target_words") or 2_000_000)
    project_info.setdefault("target_chapters", target_chapters or normalized.get("target_chapters") or "")
    project_info.setdefault("target_volumes", normalized.get("total_planned_volumes") or len(volumes_planned) or "")

    progress = dict(normalized.get("progress") or {}) if isinstance(normalized.get("progress"), dict) else {}
    progress.setdefault(
        "current_chapter",
        normalized.get("current_chapter") or normalized.get("last_completed_chapter") or 0,
    )
    progress.setdefault("current_volume", normalized.get("current_volume") or 1)
    progress.setdefault("total_words", normalized.get("total_words") or 0)
    progress.setdefault("target_chapters", target_chapters or normalized.get("target_chapters") or "")
    progress.setdefault("total_planned_volumes", normalized.get("total_planned_volumes") or len(volumes_planned) or "")
    progress.setdefault("chapter_status", normalized.get("chapter_status") or {})
    progress.setdefault("volumes_planned", volumes_planned)
    normalized["progress"] = progress

    return normalized


def _parse_json_value(raw: object, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _resolve_volume_for_chapter(state: dict, chapter: int) -> int | None:
    volume_item = _resolve_volume_item_for_chapter(state, chapter)
    if not volume_item:
        return None
    try:
        return int(volume_item.get("volume") or 0) or None
    except (TypeError, ValueError):
        return None


def _resolve_volume_item_for_chapter(state: dict, chapter: int) -> dict | None:
    progress = state.get("progress") if isinstance(state, dict) else {}
    if not isinstance(progress, dict):
        return None
    volumes_planned = progress.get("volumes_planned")
    if not isinstance(volumes_planned, list):
        return None

    best: tuple[int, int, dict] | None = None
    for item in volumes_planned:
        if not isinstance(item, dict):
            continue
        volume = _safe_int(item.get("volume"))
        if volume <= 0:
            continue
        start, end = _parse_chapter_range_bounds(item.get("chapters_range"))
        if start <= 0 or end <= 0 or start > end:
            continue
        if start <= chapter <= end:
            candidate = (start, volume, item)
            if best is None or candidate[0] > best[0] or (
                candidate[0] == best[0] and candidate[1] < best[1]
            ):
                best = candidate
    return best[2] if best else None


def _build_strand_map(state: dict) -> dict[int, str]:
    tracker = state.get("strand_tracker") if isinstance(state, dict) else {}
    history = tracker.get("history") if isinstance(tracker, dict) else []
    if not isinstance(history, list):
        return {}

    strand_map: dict[int, str] = {}
    for index, entry in enumerate(history, start=1):
        if not isinstance(entry, dict):
            continue
        chapter_value = entry.get("chapter", index)
        try:
            chapter = int(chapter_value)
        except (TypeError, ValueError):
            chapter = index
        strand = str(entry.get("strand") or entry.get("dominant") or "").strip().lower()
        if chapter > 0 and strand:
            strand_map[chapter] = strand
    return strand_map


def _extract_story_chapter(path: Path) -> int:
    match = re.search(r"chapter_(\d{3,4})", path.name)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _inspect_vector_db(project_root: Path) -> dict:
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(project_root)
    vector_db = cfg.vector_db
    exists = vector_db.is_file()
    size_bytes = vector_db.stat().st_size if exists else 0
    record_count = 0
    error = ""

    if exists and size_bytes > 0:
        try:
            with sqlite3.connect(str(vector_db)) as conn:
                cursor = conn.cursor()
                table_exists = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'vectors'"
                ).fetchone()
                if table_exists:
                    row = cursor.execute("SELECT COUNT(*) FROM vectors").fetchone()
                    record_count = int(row[0] or 0) if row else 0
        except sqlite3.Error as exc:
            error = str(exc)

    return {
        "path": str(vector_db),
        "exists": exists,
        "size_bytes": size_bytes,
        "record_count": record_count,
        "error": error,
    }


def _build_env_status(project_root: Path) -> dict:
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(project_root)
    vector_info = _inspect_vector_db(project_root)

    embed_ready = bool(str(cfg.embed_api_key or "").strip())
    rerank_ready = bool(str(cfg.rerank_api_key or "").strip())
    vector_ready = bool(vector_info["exists"] and vector_info["size_bytes"] > 0)

    if vector_ready and embed_ready and rerank_ready:
        rag_mode = "full"
    elif vector_ready and embed_ready:
        rag_mode = "embed_only"
    else:
        rag_mode = "bm25_only"

    return {
        "embed": {
            "base_url": cfg.embed_base_url,
            "model": cfg.embed_model,
            "api_key_present": embed_ready,
        },
        "rerank": {
            "base_url": cfg.rerank_base_url,
            "model": cfg.rerank_model,
            "api_key_present": rerank_ready,
        },
        "vector_db": vector_info,
        "rag_mode": rag_mode,
    }


def _read_workflow_doc(project_root: Path, rel_path: str, title: str, required: bool = True) -> dict:
    path = safe_resolve(project_root, rel_path)
    exists = path.is_file()
    content = ""
    error = ""
    if exists:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            error = str(exc)
    return {
        "title": title,
        "path": rel_path,
        "exists": exists,
        "required": required,
        "content": content,
        "error": error,
    }


def _build_workflow_status(project_root: Path) -> dict:
    docs = [
        _read_workflow_doc(project_root, "规划/写作流程.md", "写作流程"),
        _read_workflow_doc(project_root, "规划/No正文生成提示词.md", "No 正文提示词"),
        _read_workflow_doc(project_root, ".webnovel/post_chapter_update_checklist.md", "写后状态更新清单"),
        _read_workflow_doc(project_root, "设定集/技能物品时间线.md", "技能物品时间线"),
        _read_workflow_doc(project_root, "设定集/技能卡/技能卡总表.md", "技能卡总表"),
        _read_workflow_doc(project_root, "设定集/物品库/物品卡总表.md", "物品卡总表"),
        _read_workflow_doc(project_root, ".codex/skills/no-webnovel-write/SKILL.md", "Codex No 写作 Skill"),
    ]

    optional_docs = [
        _read_workflow_doc(project_root, "设定集/原作时间线.md", "原作时间线", required=False),
        _read_workflow_doc(project_root, "设定集/同人分歧点.md", "同人分歧点", required=False),
        _read_workflow_doc(project_root, "设定集/OOC禁区.md", "OOC 禁区", required=False),
        _read_workflow_doc(project_root, "设定集/平台风格约束.md", "平台风格约束", required=False),
        _read_workflow_doc(project_root, "设定集/改写边界.md", "改写边界", required=False),
    ]

    required_missing = [item["path"] for item in docs if item["required"] and not item["exists"]]
    optional_missing = [item["path"] for item in optional_docs if not item["exists"]]

    return {
        "ok": not required_missing,
        "required_missing": required_missing,
        "optional_missing": optional_missing,
        "docs": docs,
        "optional_docs": optional_docs,
    }


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------

def create_app(project_root: str | Path | None = None) -> FastAPI:
    global _project_root

    if project_root:
        _project_root = Path(project_root).resolve()

    _ensure_scripts_dir_on_path()

    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        webnovel = _webnovel_dir()
        story_system = _story_system_dir()
        if webnovel.is_dir() or story_system.is_dir():
            _watcher.start(
                watch_webnovel_dir=webnovel if webnovel.is_dir() else None,
                watch_story_system_dir=story_system if story_system.is_dir() else None,
                loop=asyncio.get_running_loop(),
            )
        try:
            yield
        finally:
            _watcher.stop()

    app = FastAPI(title="Webnovel Dashboard", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ===========================================================
    # API：项目元信息
    # ===========================================================

    @app.get("/api/project/info")
    def project_info():
        """返回 state.json 完整内容（只读）。"""
        return _load_state_payload(required=True)

    @app.get("/api/story-runtime/health")
    def story_runtime_health():
        return _build_story_runtime_health_report(_get_project_root())

    # ===========================================================
    # API：小说发布（显式操作，默认草稿）
    # ===========================================================

    from .publish_bridge import (
        check_login_status,
        check_playwright,
        close_publish_manager,
        create_book,
        get_books,
        get_remote_chapters,
        get_task_status,
        publish_chapters,
        setup_browser,
    )

    @app.get("/api/publish/status")
    def api_publish_status():
        """检查发布环境状态（不访问番茄网络，只看依赖和本地登录态）。"""
        playwright = check_playwright()
        login = check_login_status()
        return {
            "playwright": playwright,
            "login": login,
            "ready": playwright["available"] and login["logged_in"],
        }

    @app.post("/api/publish/setup-browser")
    def api_publish_setup_browser():
        """打开登录浏览器，用户手动登录番茄作家后台。"""
        task_id = setup_browser()
        return {"task_id": task_id, "status": "pending"}

    @app.get("/api/publish/books")
    def api_publish_books():
        """获取番茄作家后台书籍列表。"""
        try:
            return get_books(_get_project_root())
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/publish/books")
    def api_publish_create_book(
        title: str = Body(...),
        genre: str = Body(...),
        synopsis: str = Body(...),
        protagonist1: str = Body(""),
        protagonist2: str = Body(""),
    ):
        """创建新书。"""
        result = create_book(_get_project_root(), title, genre, synopsis, protagonist1, protagonist2)
        if result.get("success"):
            return result
        raise HTTPException(status_code=400, detail=result.get("error", "创建失败"))

    @app.get("/api/publish/books/{book_id}/remote-chapters")
    def api_remote_chapters(book_id: str):
        """获取番茄平台上的章节列表（已发布+草稿）。"""
        result = get_remote_chapters(_get_project_root(), book_id)
        if isinstance(result, dict) and "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result

    @app.post("/api/publish/chapters")
    def api_publish_chapters(
        book_id: str = Body(...),
        range_spec: str = Body("all"),
        publish_mode: str = Body("draft"),
    ):
        """发布章节（创建后台任务）。"""
        task_id = publish_chapters(_get_project_root(), book_id, range_spec, publish_mode)
        return {"task_id": task_id, "status": "pending"}

    @app.get("/api/publish/task/{task_id}")
    def api_publish_task_status(task_id: str):
        """查询发布任务进度。"""
        status = get_task_status(task_id)
        if status is None:
            raise HTTPException(404, f"任务 {task_id} 不存在")
        return status

    @app.post("/api/publish/close")
    def api_close_publish_manager():
        """显式关闭发布浏览器，释放资源。"""
        return close_publish_manager()

    # ===========================================================
    # API：小说导出
    # ===========================================================

    from .export_bridge import (
        do_export,
        get_chapter_list,
        get_export_info,
        get_output_dir,
        list_exports,
    )

    @app.get("/api/export/info")
    def api_export_info():
        """获取导出配置信息。"""
        return get_export_info(_get_project_root())

    @app.get("/api/export/chapters")
    def api_export_chapters():
        """获取可用章节列表。"""
        return get_chapter_list(_get_project_root())

    @app.post("/api/export/do")
    def api_do_export(
        format: str = Body(...),
        range_spec: str = Body("all"),
        author: str = Body(""),
        cover_path: Optional[str] = Body(None),
        style_path: Optional[str] = Body(None),
    ):
        """执行导出。"""
        result = do_export(_get_project_root(), format, range_spec, author, cover_path, style_path)
        if not result.get("success"):
            raise HTTPException(400, detail=result.get("error"))
        return result

    @app.get("/api/export/files")
    def api_list_exports():
        """列出已导出的文件。"""
        return list_exports(_get_project_root())

    @app.get("/api/export/download/{filename}")
    def api_download_export(filename: str):
        """下载导出的文件。"""
        if Path(filename).name != filename:
            raise HTTPException(403, "非法文件名")
        output_dir = get_output_dir(_get_project_root()).resolve()
        file_path = (output_dir / filename).resolve()
        try:
            file_path.relative_to(output_dir)
        except ValueError as exc:
            raise HTTPException(403, "路径越界：禁止访问导出目录之外的文件") from exc
        if not file_path.is_file():
            raise HTTPException(404, "文件不存在")
        return FileResponse(file_path, filename=filename)

    # ===========================================================
    # API：实体数据库（index.db 只读查询）
    # ===========================================================

    def _get_db() -> sqlite3.Connection:
        db_path = _webnovel_dir() / "index.db"
        if not db_path.is_file():
            raise HTTPException(404, "index.db 不存在")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _fetchall_safe(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
        """执行只读查询；若目标表不存在（旧库），返回空列表。"""
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower() or "no such column" in str(exc).lower():
                return []
            raise HTTPException(status_code=500, detail=f"数据库查询失败: {exc}") from exc

    @app.get("/api/entities")
    def list_entities(
        entity_type: Optional[str] = Query(None, alias="type"),
        include_archived: bool = False,
    ):
        """列出所有实体（可按类型过滤）。"""
        with closing(_get_db()) as conn:
            q = "SELECT * FROM entities"
            params: list = []
            clauses: list[str] = []
            if entity_type:
                clauses.append("type = ?")
                params.append(entity_type)
            if not include_archived:
                clauses.append("is_archived = 0")
            if clauses:
                q += " WHERE " + " AND ".join(clauses)
            q += " ORDER BY last_appearance DESC"
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/entities/{entity_id}")
    def get_entity(entity_id: str):
        with closing(_get_db()) as conn:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if not row:
                raise HTTPException(404, "实体不存在")
            return dict(row)

    @app.get("/api/relationships")
    def list_relationships(entity: Optional[str] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if entity:
                rows = conn.execute(
                    "SELECT * FROM relationships WHERE from_entity = ? OR to_entity = ? ORDER BY chapter DESC LIMIT ?",
                    (entity, entity, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM relationships ORDER BY chapter DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/relationship-events")
    def list_relationship_events(
        entity: Optional[str] = None,
        from_chapter: Optional[int] = None,
        to_chapter: Optional[int] = None,
        limit: int = 200,
    ):
        with closing(_get_db()) as conn:
            q = "SELECT * FROM relationship_events"
            params: list = []
            clauses: list[str] = []
            if entity:
                clauses.append("(from_entity = ? OR to_entity = ?)")
                params.extend([entity, entity])
            if from_chapter is not None:
                clauses.append("chapter >= ?")
                params.append(from_chapter)
            if to_chapter is not None:
                clauses.append("chapter <= ?")
                params.append(to_chapter)
            if clauses:
                q += " WHERE " + " AND ".join(clauses)
            q += " ORDER BY chapter DESC, id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/chapters")
    def list_chapters():
        state = _load_state_payload()
        with closing(_get_db()) as conn:
            rows = conn.execute("SELECT * FROM chapters ORDER BY chapter ASC").fetchall()
            normalized = []
            for row in rows:
                item = dict(row)
                item["characters"] = _parse_json_value(item.get("characters"), [])
                chapter_num = _safe_int(item.get("chapter"))
                volume_item = _resolve_volume_item_for_chapter(state, chapter_num)
                if volume_item:
                    item["volume"] = volume_item.get("volume")
                    item["volume_title"] = volume_item.get("title") or f"第{volume_item.get('volume')}卷"
                    item["volume_range"] = volume_item.get("chapters_range") or ""
                normalized.append(item)
            return normalized

    @app.get("/api/scenes")
    def list_scenes(chapter: Optional[int] = None, limit: int = 500):
        with closing(_get_db()) as conn:
            if chapter is not None:
                rows = conn.execute(
                    "SELECT * FROM scenes WHERE chapter = ? ORDER BY scene_index ASC", (chapter,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scenes ORDER BY chapter ASC, scene_index ASC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/reading-power")
    def list_reading_power(limit: int = 50):
        with closing(_get_db()) as conn:
            rows = conn.execute(
                "SELECT * FROM chapter_reading_power ORDER BY chapter DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/review-metrics")
    def list_review_metrics(limit: int = 20):
        with closing(_get_db()) as conn:
            rows = conn.execute(
                "SELECT * FROM review_metrics ORDER BY end_chapter DESC LIMIT ?", (limit,)
            ).fetchall()
            normalized = []
            for row in rows:
                item = dict(row)
                item["dimension_scores"] = _parse_json_value(item.get("dimension_scores"), {})
                item["severity_counts"] = _parse_json_value(item.get("severity_counts"), {})
                item["critical_issues"] = _parse_json_value(item.get("critical_issues"), [])
                normalized.append(item)
            return normalized

    @app.get("/api/stats/chapter-trend")
    def chapter_trend(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        state = _load_state_payload()
        strand_map = _build_strand_map(state)

        with closing(_get_db()) as conn:
            total_rows = _fetchall_safe(conn, "SELECT COUNT(*) AS count FROM chapters")
            latest_rows = _fetchall_safe(conn, "SELECT MAX(chapter) AS chapter FROM chapters")
            rows = _fetchall_safe(
                conn,
                """
                WITH selected_chapters AS (
                    SELECT chapter, title, location, word_count, characters, summary
                    FROM chapters
                    ORDER BY chapter DESC
                    LIMIT ? OFFSET ?
                )
                SELECT
                    c.chapter,
                    c.title,
                    c.location,
                    c.word_count,
                    c.characters,
                    c.summary,
                    rp.hook_type,
                    rp.hook_strength,
                    rp.is_transition,
                    rp.override_count,
                    rp.debt_balance,
                    rm.overall_score AS review_score,
                    rm.severity_counts
                FROM selected_chapters c
                LEFT JOIN chapter_reading_power rp ON rp.chapter = c.chapter
                LEFT JOIN review_metrics rm ON rm.end_chapter = c.chapter
                ORDER BY c.chapter ASC
                """,
                (limit, offset),
            )

        hook_strength_value = {"weak": 1, "medium": 3, "strong": 5}
        items = []
        for row in rows:
            chapter = int(row.get("chapter") or 0)
            hook_strength = str(row.get("hook_strength") or "").strip().lower()
            items.append(
                {
                    "chapter": chapter,
                    "title": row.get("title") or "",
                    "location": row.get("location") or "",
                    "word_count": int(row.get("word_count") or 0),
                    "characters": _parse_json_value(row.get("characters"), []),
                    "summary": row.get("summary") or "",
                    "review_score": row.get("review_score"),
                    "review_severity_counts": _parse_json_value(row.get("severity_counts"), {}),
                    "hook_type": row.get("hook_type") or "",
                    "hook_strength": hook_strength,
                    "hook_strength_value": hook_strength_value.get(hook_strength, 0),
                    "is_transition": bool(row.get("is_transition")),
                    "override_count": int(row.get("override_count") or 0),
                    "debt_balance": float(row.get("debt_balance") or 0.0),
                    "strand": strand_map.get(chapter, ""),
                    "volume": _resolve_volume_for_chapter(state, chapter),
                }
            )

        return {
            "items": items,
            "total": int(total_rows[0]["count"] or 0) if total_rows else 0,
            "latest_chapter": int(latest_rows[0]["chapter"] or 0) if latest_rows else 0,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/commits")
    def list_commits(limit: int = Query(20, ge=1, le=200)):
        commits_dir = _story_system_dir() / "commits"
        if not commits_dir.is_dir():
            return {"items": [], "total": 0, "limit": limit}

        items = []
        for path in commits_dir.glob("chapter_*.commit.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            meta = payload.get("meta") if isinstance(payload, dict) else {}
            provenance = payload.get("provenance") if isinstance(payload, dict) else {}
            chapter = int((meta or {}).get("chapter") or _extract_story_chapter(path))
            items.append(
                {
                    "chapter": chapter,
                    "status": str((meta or {}).get("status") or "missing"),
                    "projection_status": payload.get("projection_status") or {},
                    "write_fact_role": str((provenance or {}).get("write_fact_role") or ""),
                    "contract_refs": payload.get("contract_refs") or {},
                    "path": path.name,
                    "updated_at": datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )

        items.sort(key=lambda item: item["chapter"], reverse=True)
        return {"items": items[:limit], "total": len(items), "limit": limit}

    @app.get("/api/contracts/summary")
    def contracts_summary():
        from data_modules.story_contracts import StoryContractPaths, read_json_if_exists

        project_root = _get_project_root()
        state = _load_state_payload()
        runtime = _build_story_runtime_health_report(project_root)
        chapter = int(runtime.get("chapter") or ((state.get("progress") or {}).get("current_chapter") or 0))
        current_volume = _resolve_volume_for_chapter(state, chapter) or int(
            ((state.get("progress") or {}).get("current_volume") or 1)
        )

        paths = StoryContractPaths.from_project_root(project_root)
        master_payload = read_json_if_exists(paths.master_json) or {}
        genre_value = (master_payload.get("route") or {}).get("primary_genre")
        if not genre_value:
            raw_genre = master_payload.get("genre") or ""
            genre_value = "、".join(raw_genre) if isinstance(raw_genre, list) else str(raw_genre)
        tone_value = (master_payload.get("master_constraints") or {}).get("core_tone")
        if not tone_value:
            tone = master_payload.get("tone") or {}
            if isinstance(tone, dict):
                tone_value = tone.get("style") or tone.get("prose") or ""

        chapter_paths = paths.chapter_json_candidates(chapter) if chapter > 0 else []
        review_paths = paths.review_json_candidates(chapter) if chapter > 0 else []
        chapter_count = len(
            {
                _extract_story_chapter(path)
                for path in paths.chapters_dir.glob("chapter_*.json")
                if path.is_file() and _extract_story_chapter(path) > 0
            }
        ) if paths.chapters_dir.is_dir() else 0
        review_count = len(
            {
                _extract_story_chapter(path)
                for path in paths.reviews_dir.glob("chapter_*.json")
                if path.is_file() and _extract_story_chapter(path) > 0
            }
        ) if paths.reviews_dir.is_dir() else 0

        return {
            "chapter": chapter,
            "current_volume": current_volume,
            "master": {
                "exists": bool(master_payload),
                "primary_genre": str(genre_value or ""),
                "core_tone": str(tone_value or ""),
            },
            "counts": {
                "volumes": len(list(paths.volumes_dir.glob("volume_*.json"))) if paths.volumes_dir.is_dir() else 0,
                "chapters": chapter_count,
                "reviews": review_count,
                "commits": len(list(paths.commits_dir.glob("chapter_*.commit.json"))) if paths.commits_dir.is_dir() else 0,
            },
            "current_contracts": {
                "volume": paths.volume_json(current_volume).is_file(),
                "chapter": any(path.is_file() for path in chapter_paths),
                "review": any(path.is_file() for path in review_paths),
                "commit": paths.commit_json(chapter).is_file() if chapter > 0 else False,
            },
        }

    @app.get("/api/env-status")
    def env_status():
        return _build_env_status(_get_project_root())

    @app.get("/api/env-status/probe")
    def env_status_probe():
        status = _build_env_status(_get_project_root())
        runtime = _build_story_runtime_health_report(_get_project_root())
        vector_db = status["vector_db"]
        checks = [
            {
                "name": "embed_api_key",
                "ok": bool(status["embed"]["api_key_present"]),
                "detail": "已配置" if status["embed"]["api_key_present"] else "未配置",
            },
            {
                "name": "rerank_api_key",
                "ok": bool(status["rerank"]["api_key_present"]),
                "detail": "已配置" if status["rerank"]["api_key_present"] else "未配置",
            },
            {
                "name": "vector_db",
                "ok": bool(vector_db["exists"] and not vector_db["error"]),
                "detail": vector_db["error"]
                or f"{vector_db['record_count']} records · {vector_db['size_bytes']} bytes",
            },
            {
                "name": "story_runtime",
                "ok": bool(runtime.get("mainline_ready")),
                "detail": (
                    f"chapter={runtime.get('chapter')} "
                    f"status={runtime.get('latest_commit_status')} "
                    f"fallback={','.join(runtime.get('fallback_sources') or []) or 'none'}"
                ),
            },
        ]
        return {
            "ok": all(bool(item["ok"]) for item in checks),
            "rag_mode": status["rag_mode"],
            "checks": checks,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/workflow")
    def workflow_status():
        """返回当前项目的写作流程、No 提示词、写后清单和 Codex skill 状态。"""
        return _build_workflow_status(_get_project_root())

    @app.get("/api/state-changes")
    def list_state_changes(entity: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if entity:
                rows = conn.execute(
                    "SELECT * FROM state_changes WHERE entity_id = ? ORDER BY chapter DESC LIMIT ?",
                    (entity, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM state_changes ORDER BY chapter DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/aliases")
    def list_aliases(entity: Optional[str] = None):
        with closing(_get_db()) as conn:
            if entity:
                rows = conn.execute(
                    "SELECT * FROM aliases WHERE entity_id = ?", (entity,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM aliases").fetchall()
            return [dict(r) for r in rows]

    # ===========================================================
    # API：扩展表（v5.3+ / v5.4+）
    # ===========================================================

    @app.get("/api/overrides")
    def list_overrides(status: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if status:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM override_contracts WHERE status = ? ORDER BY chapter DESC LIMIT ?",
                    (status, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM override_contracts ORDER BY chapter DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/debts")
    def list_debts(status: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if status:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM chase_debt WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                    (status, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM chase_debt ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/debt-events")
    def list_debt_events(debt_id: Optional[int] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if debt_id is not None:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM debt_events WHERE debt_id = ? ORDER BY chapter DESC, id DESC LIMIT ?",
                    (debt_id, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM debt_events ORDER BY chapter DESC, id DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/invalid-facts")
    def list_invalid_facts(status: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if status:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM invalid_facts WHERE status = ? ORDER BY marked_at DESC LIMIT ?",
                    (status, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM invalid_facts ORDER BY marked_at DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/rag-queries")
    def list_rag_queries(query_type: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if query_type:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM rag_query_log WHERE query_type = ? ORDER BY created_at DESC LIMIT ?",
                    (query_type, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM rag_query_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/tool-stats")
    def list_tool_stats(tool_name: Optional[str] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if tool_name:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM tool_call_stats WHERE tool_name = ? ORDER BY created_at DESC LIMIT ?",
                    (tool_name, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM tool_call_stats ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/checklist-scores")
    def list_checklist_scores(limit: int = 100):
        with closing(_get_db()) as conn:
            return _fetchall_safe(
                conn,
                "SELECT * FROM writing_checklist_scores ORDER BY chapter DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/story-events")
    def list_story_events(chapter: Optional[int] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if chapter is not None:
                rows = _fetchall_safe(
                    conn,
                    """
                    SELECT event_id, chapter, event_type, subject, payload_json, created_at
                    FROM story_events
                    WHERE chapter = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (chapter, limit),
                )
            else:
                rows = _fetchall_safe(
                    conn,
                    """
                    SELECT event_id, chapter, event_type, subject, payload_json, created_at
                    FROM story_events
                    ORDER BY chapter DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

        normalized = []
        for row in rows:
            payload = {}
            try:
                payload = json.loads(row.get("payload_json") or "{}")
            except json.JSONDecodeError:
                payload = {}
            normalized.append({**row, "payload": payload})
        return normalized

    @app.get("/api/story-events/health")
    def story_event_health():
        with closing(_get_db()) as conn:
            event_rows = _fetchall_safe(conn, "SELECT COUNT(*) AS count FROM story_events")
            proposal_rows = _fetchall_safe(
                conn,
                """
                SELECT COUNT(*) AS count
                FROM override_contracts
                WHERE record_type = 'amend_proposal' AND status = 'pending'
                """,
            )

        events_dir = _story_system_dir() / "events"
        file_count = len(list(events_dir.glob("chapter_*.events.json"))) if events_dir.is_dir() else 0
        return {
            "story_events": event_rows[0]["count"] if event_rows else 0,
            "pending_amend_proposals": proposal_rows[0]["count"] if proposal_rows else 0,
            "event_files": file_count,
        }

    # ===========================================================
    # API：文档浏览（正文/大纲/设定集 —— 只读）
    # ===========================================================

    @app.get("/api/files/tree")
    def file_tree():
        """列出 正文/、大纲/、设定集/ 三个目录的树结构。"""
        root = _get_project_root()
        result = {}
        for folder_name in ("正文", "大纲", "设定集"):
            folder = root / folder_name
            if not folder.is_dir():
                result[folder_name] = []
                continue
            if folder_name == "正文":
                result[folder_name] = _build_chapter_volume_tree(folder, root)
            else:
                result[folder_name] = _walk_tree(folder, root)
        return result

    @app.get("/api/files/read")
    def file_read(path: str):
        """只读读取一个文件内容（限 正文/大纲/设定集 目录）。"""
        root = _get_project_root()
        resolved = safe_resolve(root, path)
        if _has_hidden_path_segment(resolved, root):
            raise HTTPException(404, "文件不存在")

        # 二次限制：只允许三大目录
        allowed_parents = [root / n for n in ("正文", "大纲", "设定集")]
        if not any(_is_child(resolved, p) for p in allowed_parents):
            raise HTTPException(403, "仅允许读取 正文/大纲/设定集 目录下的文件")

        if not resolved.is_file():
            raise HTTPException(404, "文件不存在")

        # 文本文件直接读；其他情况返回占位信息
        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = "[二进制文件，无法预览]"

        return {"path": path, "content": content}

    # ===========================================================
    # SSE：实时变更推送
    # ===========================================================

    @app.get("/api/events")
    async def sse():
        """Server-Sent Events 端点，推送 .webnovel/.story-system 的文件变更。"""
        q = _watcher.subscribe()

        async def _gen():
            try:
                while True:
                    msg = await q.get()
                    yield f"data: {msg}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                _watcher.unsubscribe(q)

        return StreamingResponse(_gen(), media_type="text/event-stream")

    # ===========================================================
    # 前端静态文件托管
    # ===========================================================

    if STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str):
            """SPA fallback：任何非 /api 路径都返回 index.html。"""
            if full_path.startswith("api/"):
                raise HTTPException(404, "API 路径不存在")
            index = STATIC_DIR / "index.html"
            if index.is_file():
                return FileResponse(str(index))
            raise HTTPException(404, "前端尚未构建")
    else:
        @app.get("/")
        def no_frontend():
            return HTMLResponse(
                "<h2>Webnovel Dashboard API is running</h2>"
                "<p>前端尚未构建。请先在 <code>dashboard/frontend</code> 目录执行 <code>npm run build</code>。</p>"
                '<p>API 文档：<a href="/docs">/docs</a></p>'
            )

    return app


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _walk_tree(folder: Path, root: Path) -> list[dict]:
    items = []
    for child in sorted(folder.iterdir()):
        if child.name.startswith("."):
            continue
        rel = str(child.relative_to(root)).replace("\\", "/")
        if child.is_dir():
            items.append({"name": child.name, "type": "dir", "path": rel, "children": _walk_tree(child, root)})
        else:
            items.append({"name": child.name, "type": "file", "path": rel, "size": child.stat().st_size})
    return items


def _build_chapter_volume_tree(folder: Path, root: Path) -> list[dict]:
    files = sorted(
        _iter_file_entries(folder, root),
        key=lambda item: (_chapter_number_from_filename(item["name"]) or 10**9, item["path"]),
    )
    volumes = _infer_volumes_planned(root)
    if not files or not volumes:
        return files

    grouped: list[dict] = []
    assigned_paths = set()
    for volume in volumes:
        start, end = _parse_chapter_range_bounds(volume.get("chapters_range"))
        if not start or not end:
            continue
        children = [
            item
            for item in files
            if start <= (_chapter_number_from_filename(item["name"]) or -1) <= end
        ]
        if not children:
            continue
        assigned_paths.update(item["path"] for item in children)
        volume_num = int(volume.get("volume") or len(grouped) + 1)
        grouped.append(
            {
                "name": str(volume.get("title") or f"第{volume_num}卷"),
                "type": "dir",
                "path": f"正文/__volume_{volume_num}",
                "children": children,
            }
        )

    unassigned = [item for item in files if item["path"] not in assigned_paths]
    if unassigned:
        grouped.append(
            {
                "name": "未分卷章节",
                "type": "dir",
                "path": "正文/__volume_unassigned",
                "children": unassigned,
            }
        )
    return grouped or files


def _iter_file_entries(folder: Path, root: Path):
    for child in sorted(folder.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            yield from _iter_file_entries(child, root)
            continue
        rel = str(child.relative_to(root)).replace("\\", "/")
        yield {"name": child.name, "type": "file", "path": rel, "size": child.stat().st_size}


def _chapter_number_from_filename(name: str) -> int:
    match = re.search(r"第\s*0*(\d+)\s*章", name)
    if not match:
        match = re.search(r"chapter[_-]?0*(\d+)", name, flags=re.IGNORECASE)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _has_hidden_path_segment(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return True
    return any(part.startswith(".") for part in relative_parts)


def _is_child(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
