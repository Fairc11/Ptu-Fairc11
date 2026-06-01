import re
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pathlib import Path
from ..models.task_store import get_store
from ..models.schemas import TaskStatus
from ..services.downloader import download_manager
from ..config import settings

router = APIRouter(prefix="/api", tags=["download"])


def _safe_filename(s: str) -> str:
    """Remove characters unsafe for Windows folder names."""
    return re.sub(r'[<>:"/\\|?*]', '', s).strip() or "unknown"


def _build_folder_name(task) -> str:
    """Build folder name: {date}_{title}_{task_id_short}."""
    # 优先使用作品发布时间，降级用抓取时间
    if task.metadata and getattr(task.metadata, 'create_time', 0):
        date_str = datetime.fromtimestamp(task.metadata.create_time).strftime("%Y-%m-%d")
    else:
        date_str = task.created_at.strftime("%Y-%m-%d") if hasattr(task.created_at, 'strftime') else datetime.now().strftime("%Y-%m-%d")
    # 取标题前25字（去掉 #话题），没有则用作者名
    label = ""
    if task.metadata:
        if task.metadata.title:
            label = re.sub(r'[#＃]\S*', '', task.metadata.title).strip()[:25]
        if not label and task.metadata.author:
            label = task.metadata.author
    if not label:
        label = "unknown"
    label = _safe_filename(label)
    tid = task.task_id[:8] if task.task_id else "unknown"
    return f"{date_str}_{label}_{tid}"


@router.post("/tasks/{task_id}/download")
async def download_files(task_id: str):
    """Download all files for a scraped task."""
    store = get_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(404, "任务未找到")
    if not task.metadata or not task.metadata.image_urls:
        raise HTTPException(400, "请先抓取内容")

    try:
        store.update_status(task_id, TaskStatus.DOWNLOADING)

        folder = _build_folder_name(task)
        target_dir = settings.download_dir / folder
        result = await download_manager.download_all(
            task_id, task.metadata, target_dir
        )

        store.update_status(
            task_id, TaskStatus.DOWNLOADED,
            download_path=str(target_dir)
        )

        return {
            "status": "ok",
            "task_id": task_id,
            "download_path": str(target_dir),
            "folder": folder,
            "files": result,
        }

    except Exception as e:
        store.update_status(task_id, TaskStatus.ERROR, error_message=str(e))
        raise HTTPException(500, f"下载失败: {str(e)}")
