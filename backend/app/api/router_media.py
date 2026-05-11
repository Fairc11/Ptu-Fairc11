import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from ..models.task_store import get_store
from ..models.schemas import TaskStatus, RenderRequest, RenderOptions
from ..services.media_processor import media_processor
from ..services.live_photo import live_photo_processor
from ..config import settings

router = APIRouter(prefix="/api", tags=["media"])


@router.post("/tasks/{task_id}/render")
async def render_video(task_id: str, req: RenderRequest):
    """Render slideshow video from downloaded files."""
    store = get_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(404, "任务未找到")

    download_path = Path(task.download_path) if task.download_path else None
    if not download_path or not download_path.exists():
        raise HTTPException(400, "请先下载素材")

    images_dir = download_path / "images"
    if not images_dir.exists():
        raise HTTPException(400, "图片目录未找到")

    # Collect images
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
    image_paths = sorted(
        [str(p) for p in images_dir.iterdir() if p.suffix.lower() in image_extensions]
    )

    if not image_paths:
        raise HTTPException(400, "未找到图片")

    options = req.options

    # Convert HEIC images to JPEG
    for i, path in enumerate(image_paths):
        if live_photo_processor.is_heic(path):
            jpeg_path = live_photo_processor.convert_heic_to_jpeg(path, images_dir)
            image_paths[i] = jpeg_path

    # Music path
    music_path = None
    if options.use_original_music and options.music_file:
        mp = Path(options.music_file)
        if mp.exists():
            music_path = str(mp)
    elif options.use_original_music:
        music_dir = download_path / "music"
        possible = list(music_dir.glob("*"))
        if possible:
            music_path = str(possible[0])

    # Live photo videos
    live_videos = []
    live_dir = download_path / "live_photos"
    if live_dir.exists():
        live_videos = sorted([str(p) for p in live_dir.iterdir()])

    try:
        store.update_status(task_id, TaskStatus.PROCESSING)

        output_dir = settings.output_dir / task_id
        output_path = await media_processor.render_slideshow(
            task_id=task_id,
            image_paths=image_paths,
            music_path=music_path,
            options=options,
            output_dir=output_dir,
            live_photo_videos=live_videos,
        )

        store.update_status(
            task_id, TaskStatus.COMPLETED,
            output_path=output_path
        )

        return {
            "status": "ok",
            "task_id": task_id,
            "output_path": output_path,
            "image_count": len(image_paths),
        }

    except Exception as e:
        store.update_status(task_id, TaskStatus.ERROR, error_message=str(e))
        raise HTTPException(500, f"渲染失败: {str(e)}")
