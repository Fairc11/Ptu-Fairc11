import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from ..models.task_store import get_store
from ..models.schemas import TaskStatus, RenderRequest, RenderOptions
from ..services.media_processor import media_processor
from ..services.live_photo import live_photo_processor
from ..config import settings

router = APIRouter(prefix="/api", tags=["media"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}


def _user_visible_images(folder: Path, *, live_photo_stem: bool = False) -> list[str]:
    """Return renderable image files while hiding converted WEBP/HEIC originals."""
    if not folder.exists():
        return []
    files = [
        p for p in sorted(folder.iterdir())
        if p.suffix.lower() in IMAGE_EXTENSIONS
        and (not live_photo_stem or p.stem.endswith("_img"))
    ]
    stems_with_jpeg = {
        p.stem for p in files
        if p.suffix.lower() in {".jpg", ".jpeg"}
    }
    visible: list[str] = []
    for path in files:
        if path.suffix.lower() in {".webp", ".heic", ".heif"} and path.stem in stems_with_jpeg:
            continue
        visible.append(str(path))
    return visible


def _collect_render_media(download_path: Path) -> tuple[list[str], list[str]]:
    image_paths: list[str] = []
    live_video_paths: list[str] = []

    images_dir = download_path / "images"
    image_paths.extend(_user_visible_images(images_dir))

    live_dir = download_path / "live_photos"
    if live_dir.exists():
        image_paths.extend(_user_visible_images(live_dir, live_photo_stem=True))
        live_video_paths.extend(
            str(p) for p in sorted(live_dir.iterdir())
            if p.suffix.lower() in VIDEO_EXTENSIONS and p.stem.endswith("_vid")
        )

    return image_paths, live_video_paths


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

    image_paths, live_videos = _collect_render_media(download_path)

    if not image_paths and not live_videos:
        raise HTTPException(400, "未找到图片或实况视频")

    options = req.options

    # Convert HEIC images to JPEG
    for i, path in enumerate(image_paths):
        if live_photo_processor.is_heic(path):
            jpeg_path = live_photo_processor.convert_heic_to_jpeg(path, Path(path).parent)
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

    try:
        store.update_status(task_id, TaskStatus.PROCESSING)

        output_dir = download_path
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
        render_meta = getattr(media_processor, "last_render_metadata", {}) or {}

        return {
            "status": "ok",
            "task_id": task_id,
            "output_path": output_path,
            "output_file": render_meta.get("output_filename") or Path(output_path).name,
            "image_count": len(image_paths),
            "visual_count": render_meta.get("visual_count", len(image_paths)),
            "live_video_count": render_meta.get("live_video_count", len(live_videos)),
            "music_duration_seconds": render_meta.get("music_duration_seconds"),
            "cycle_count": render_meta.get("cycle_count", 1),
            "ffmpeg_path": render_meta.get("ffmpeg_path"),
        }

    except Exception as e:
        store.update_status(task_id, TaskStatus.ERROR, error_message=str(e))
        raise HTTPException(500, f"渲染失败: {str(e)}")
