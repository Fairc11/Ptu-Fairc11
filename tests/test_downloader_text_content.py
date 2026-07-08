from __future__ import annotations

import subprocess

import pytest

from backend.app.models.schemas import LivePhotoSource, MediaType, ScrapeResult
from backend.app.services.downloader import DownloadManager


@pytest.mark.asyncio
async def test_video_download_saves_post_text(tmp_path, monkeypatch):
    manager = DownloadManager()

    async def fake_get_client():
        return object()

    async def fake_download_file(client, url, target_dir, prefix):
        path = target_dir / f"{prefix}.mp4"
        path.write_bytes(b"fake")
        return str(path)

    monkeypatch.setattr(manager, "_get_client", fake_get_client)
    monkeypatch.setattr(manager, "_download_file", fake_download_file)

    result = await manager.download_all(
        "task-video",
        ScrapeResult(
            title="video title",
            media_type=MediaType.VIDEO,
            image_urls=["https://example.test/cover.jpg"],
            music_url="https://example.test/video.mp4",
            text_content="完整视频文案 #话题",
        ),
        tmp_path,
    )

    assert (tmp_path / "post.txt").read_text(encoding="utf-8") == "完整视频文案 #话题"
    assert result["text_path"] == str(tmp_path / "post.txt")


@pytest.mark.asyncio
async def test_live_photo_download_saves_post_text(tmp_path, monkeypatch):
    manager = DownloadManager()

    async def fake_get_client():
        return object()

    async def fake_download_file(client, url, target_dir, prefix):
        ext = ".mp4" if prefix.endswith("_vid") or prefix == "music" else ".jpg"
        path = target_dir / f"{prefix}{ext}"
        path.write_bytes(b"fake")
        return str(path)

    async def fake_synthesize(image_path, video_path, output_path):
        return None

    monkeypatch.setattr(manager, "_get_client", fake_get_client)
    monkeypatch.setattr(manager, "_download_file", fake_download_file)
    monkeypatch.setattr(manager, "_synthesize_live_photo", fake_synthesize)

    result = await manager.download_all(
        "task-live",
        ScrapeResult(
            title="live title",
            media_type=MediaType.LIVE_PHOTO,
            image_urls=["https://example.test/1.jpg"],
            live_photo_data=[
                LivePhotoSource(
                    image_url="https://example.test/1.jpg",
                    video_url="https://example.test/1.mp4",
                )
            ],
            music_url="https://example.test/music.mp3",
            text_content="完整实况文案",
        ),
        tmp_path,
    )

    assert (tmp_path / "post.txt").read_text(encoding="utf-8") == "完整实况文案"
    assert result["text_path"] == str(tmp_path / "post.txt")


@pytest.mark.asyncio
async def test_mixed_normal_images_and_live_photos_download_to_separate_folders(tmp_path, monkeypatch):
    manager = DownloadManager()

    async def fake_get_client():
        return object()

    async def fake_download_file(client, url, target_dir, prefix):
        ext = ".mp4" if prefix.endswith("_vid") or prefix == "music" else ".jpg"
        path = target_dir / f"{prefix}{ext}"
        path.write_bytes(url.encode("utf-8"))
        return str(path)

    async def fake_synthesize(image_path, video_path, output_path):
        return None

    monkeypatch.setattr(manager, "_get_client", fake_get_client)
    monkeypatch.setattr(manager, "_download_file", fake_download_file)
    monkeypatch.setattr(manager, "_synthesize_live_photo", fake_synthesize)

    result = await manager.download_all(
        "task-mixed",
        ScrapeResult(
            title="mixed",
            media_type=MediaType.COMPREHENSIVE,
            image_urls=["https://example.test/normal.jpg"],
            live_photo_data=[
                LivePhotoSource(
                    image_url="https://example.test/live.jpg",
                    video_url="https://example.test/live.mp4",
                )
            ],
        ),
        tmp_path,
    )

    assert (tmp_path / "images" / "image_0000.jpg").exists()
    assert (tmp_path / "live_photos" / "live_0000_img.jpg").exists()
    assert (tmp_path / "live_photos" / "live_0000_vid.mp4").exists()
    assert len(result["images"]) == 2
    assert len(result["live_photo_videos"]) == 1


@pytest.mark.asyncio
async def test_image_only_live_photo_data_is_downloaded_as_normal_images(tmp_path, monkeypatch):
    manager = DownloadManager()

    async def fake_get_client():
        return object()

    async def fake_download_file(client, url, target_dir, prefix):
        path = target_dir / f"{prefix}.jpg"
        path.write_bytes(url.encode("utf-8"))
        return str(path)

    monkeypatch.setattr(manager, "_get_client", fake_get_client)
    monkeypatch.setattr(manager, "_download_file", fake_download_file)

    result = await manager.download_all(
        "task-image-only-live",
        ScrapeResult(
            title="image only",
            media_type=MediaType.LIVE_PHOTO,
            live_photo_data=[
                LivePhotoSource(
                    image_url="https://example.test/not-live.webp",
                    video_url="",
                )
            ],
        ),
        tmp_path,
    )

    assert (tmp_path / "images" / "image_0000.jpg").exists()
    assert not (tmp_path / "live_photos").exists()
    assert len(result["images"]) == 1
    assert result["live_photo_videos"] == []


@pytest.mark.asyncio
async def test_image_download_uses_title_when_text_content_missing(tmp_path, monkeypatch):
    manager = DownloadManager()

    async def fake_get_client():
        return object()

    async def fake_download_file(client, url, target_dir, prefix):
        path = target_dir / f"{prefix}.jpg"
        path.write_bytes(b"fake")
        return str(path)

    monkeypatch.setattr(manager, "_get_client", fake_get_client)
    monkeypatch.setattr(manager, "_download_file", fake_download_file)

    result = await manager.download_all(
        "task-image",
        ScrapeResult(
            title="只有标题也要保存",
            media_type=MediaType.IMAGE_SET,
            image_urls=["https://example.test/1.jpg"],
        ),
        tmp_path,
    )

    assert (tmp_path / "post.txt").read_text(encoding="utf-8") == "只有标题也要保存"
    assert result["text_path"] == str(tmp_path / "post.txt")


@pytest.mark.asyncio
async def test_live_photo_synthesis_command_normalizes_video_for_ffmpeg(tmp_path, monkeypatch):
    manager = DownloadManager()
    image = tmp_path / "live_0000_img.jpg"
    video = tmp_path / "live_0000_vid.mp4"
    output = tmp_path / "live_0000.mp4"
    image.write_bytes(b"fake-image")
    video.write_bytes(b"fake-video")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        output.write_bytes(b"fake-output")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)

    await manager._synthesize_live_photo(str(image), str(video), str(output))

    command_text = " ".join(captured["cmd"])
    assert "fps=30" in command_text
    assert "format=yuv420p" in command_text
    assert "settb=AVTB" in command_text
    assert "force_divisible_by=2" in command_text
    assert "pad=1080:1920" in command_text
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["errors"] == "replace"


@pytest.mark.asyncio
async def test_live_photo_synthesis_error_keeps_actionable_ffmpeg_lines(tmp_path, monkeypatch):
    manager = DownloadManager()
    image = tmp_path / "live_0000_img.jpg"
    video = tmp_path / "live_0000_vid.mp4"
    output = tmp_path / "live_0000.mp4"
    image.write_bytes(b"fake-image")
    video.write_bytes(b"fake-video")

    def fake_run(cmd, **kwargs):
        stderr = "\n".join(
            [
                "ffmpeg version x",
                "[Parsed_concat_5 @ 000001] Input link in0:v0 parameters do not match",
                "Error while filtering: Invalid argument",
                "Conversion failed!",
            ]
        )
        return subprocess.CompletedProcess(cmd, 1, "", stderr)

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        await manager._synthesize_live_photo(str(image), str(video), str(output))

    message = str(exc_info.value)
    assert "Input link in0:v0 parameters do not match" in message
    assert "Error while filtering: Invalid argument" in message
    assert "Conversion failed!" in message
