from __future__ import annotations

import pytest

from backend.app.api import router_media
from backend.app.api.router_media import _collect_render_media, render_video
from backend.app.models.schemas import RenderRequest, TaskInfo, TaskStatus


def test_collect_render_media_uses_live_photo_assets_when_images_dir_is_empty(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    live_dir = tmp_path / "live_photos"
    live_dir.mkdir()
    live_image = live_dir / "live_0000_img.jpg"
    live_image.write_bytes(b"fake-image")
    live_video = live_dir / "live_0000_vid.mp4"
    live_video.write_bytes(b"fake-video")
    synthesized = live_dir / "live_0000.mp4"
    synthesized.write_bytes(b"fake-synth")

    image_paths, live_video_paths = _collect_render_media(tmp_path)

    assert image_paths == [str(live_image)]
    assert live_video_paths == [str(live_video)]


def test_collect_render_media_hides_converted_webp_originals(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    webp = images_dir / "image_0000.webp"
    jpg = images_dir / "image_0000.jpg"
    webp.write_bytes(b"webp")
    jpg.write_bytes(b"jpg")

    image_paths, live_video_paths = _collect_render_media(tmp_path)

    assert image_paths == [str(jpg)]
    assert live_video_paths == []


@pytest.mark.asyncio
async def test_render_video_returns_user_visible_render_details(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "image.jpg"
    image.write_bytes(b"fake-image")

    task = TaskInfo(task_id="task-ui", share_url="https://example.test", download_path=str(tmp_path))

    class FakeStore:
        def get(self, task_id):
            return task

        def update_status(self, task_id, status, **kwargs):
            task.status = status
            for key, value in kwargs.items():
                setattr(task, key, value)

    async def fake_render_slideshow(**kwargs):
        router_media.media_processor.last_render_metadata = {
            "output_filename": "douyin_slideshow.mp4",
            "music_duration_seconds": 12.5,
            "cycle_count": 5,
            "visual_count": 2,
            "live_video_count": 1,
            "ffmpeg_path": "C:/Ptu/ffmpeg.exe",
        }
        out = tmp_path / "out" / "douyin_slideshow.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-output")
        return str(out)

    monkeypatch.setattr(router_media, "get_store", lambda: FakeStore())
    monkeypatch.setattr(router_media.media_processor, "render_slideshow", fake_render_slideshow)

    response = await render_video("task-ui", RenderRequest())

    assert response["status"] == "ok"
    assert response["output_file"] == "douyin_slideshow.mp4"
    assert response["music_duration_seconds"] == 12.5
    assert response["cycle_count"] == 5
    assert response["visual_count"] == 2
    assert response["live_video_count"] == 1
    assert task.status == TaskStatus.COMPLETED
