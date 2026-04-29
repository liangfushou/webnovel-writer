"""
Export Bridge — Dashboard 与导出系统之间的桥接层。
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

def get_output_dir(project_root: Path) -> Path:
    """Return the book-local export directory."""
    output_dir = project_root / "导出"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _get_export_manager(project_root: Path):
    """获取 ExportManager 实例"""
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    scripts_entry = str(scripts_dir)
    if scripts_entry not in sys.path:
        sys.path.insert(0, scripts_entry)
    from export_manager import ExportManager

    return ExportManager(str(project_root))


def get_chapter_list(project_root: Path) -> List[int]:
    """获取可用章节列表"""
    em = _get_export_manager(project_root)
    return em.get_chapter_list()


def get_export_info(project_root: Path) -> Dict[str, Any]:
    """获取导出信息（章节数量、可选格式等）"""
    chapters = get_chapter_list(project_root)
    return {
        "chapter_count": len(chapters),
        "chapter_range": f"1-{max(chapters) if chapters else 0}",
        "chapter_min": min(chapters) if chapters else 0,
        "chapter_max": max(chapters) if chapters else 0,
        "formats": ["txt", "markdown", "epub"],
        "output_dir": str(get_output_dir(project_root)),
        "cover_exists": (project_root / "cover.jpg").exists(),
        "cover_png_exists": (project_root / "cover.png").exists(),
        "style_exists": (project_root / "style.css").exists(),
    }


def do_export(
    project_root: Path,
    format: str,
    range_spec: str = "all",
    author: str = "",
    cover_path: Optional[str] = None,
    style_path: Optional[str] = None,
) -> Dict[str, Any]:
    """执行导出操作"""
    em = _get_export_manager(project_root)
    chapters = em.parse_chapter_range(range_spec)

    if not chapters:
        return {"success": False, "error": "没有可导出的章节"}

    filename = f"{project_root.name}.{format}"
    output_path = get_output_dir(project_root) / filename

    try:
        if format == "txt":
            count = em.export_to_txt(chapters, str(output_path))
        elif format == "markdown":
            count = em.export_to_markdown(chapters, str(output_path))
        elif format == "epub":
            auto_cover = None
            if cover_path:
                auto_cover = cover_path
            elif (project_root / "cover.jpg").exists():
                auto_cover = str(project_root / "cover.jpg")
            elif (project_root / "cover.png").exists():
                auto_cover = str(project_root / "cover.png")

            auto_style = None
            if style_path:
                auto_style = style_path
            elif (project_root / "style.css").exists():
                auto_style = str(project_root / "style.css")

            count = em.export_to_epub(
                chapters, str(output_path),
                author=author or "未知作者",
                cover_path=auto_cover,
                style_path=auto_style,
            )
        else:
            return {"success": False, "error": f"不支持的格式: {format}"}

        return {
            "success": True,
            "filename": filename,
            "file_path": str(output_path),
            "chapter_count": count,
            "chapter_range": range_spec,
            "file_size": output_path.stat().st_size,
            "format": format,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_exports(project_root: Path) -> List[Dict[str, Any]]:
    """列出已导出的文件"""
    exports = []
    for f in get_output_dir(project_root).glob(f"{project_root.name}.*"):
        exports.append({
            "filename": f.name,
            "format": f.suffix[1:],
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        })
    return sorted(exports, key=lambda x: x["modified"], reverse=True)
