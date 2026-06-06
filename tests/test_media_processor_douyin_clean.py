from __future__ import annotations

import subprocess
import logging

import pytest

from backend.app.models.schemas import RenderOptions
from backend.app.services.media_processor import MediaProcessor


def test_render_options_default_to_vertical_douyin_canvas():
    assert RenderOptions().resolution == "1080x1920"


def test_douyin_clean_command_repeats_multiple_visuals_until_music_ends(tmp_path, monkeypatch):
    images = []
    for index in range(2):
        img = tmp_path / f"image_{index}.jpg"
        img.write_bytes(b"fake-image")
        images.append(str(img))
    music = tmp_path / "music.mp3"
    music.write_bytes(b"fake-music")
    output = tmp_path / "out.mp4"

    processor = MediaProcessor()
    monkeypatch.setattr(processor, "_probe_duration", lambda path: 10.0)

    command, metadata = processor._build_douyin_clean_command(
        visual_paths=images,
        music=str(music),
        options=RenderOptions(image_duration=2.6, resolution="1080x1920", fps=30),
        output=str(output),
    )

    command_text = " ".join(command)
    assert metadata["music_duration_seconds"] == 10.0
    assert metadata["cycle_count"] == 2
    assert command.count("-loop") == 4
    assert "-t" in command
    assert "10.000" in command
    assert "scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2:flags=lanczos,crop=1080:1920" in command_text
    assert "xfade=transition=wipeleft" in command_text
    assert "-crf 18" in command_text
    assert metadata["transition"] == "wipeleft"


def test_douyin_clean_command_single_visual_holds_without_flip_transition(tmp_path, monkeypatch):
    img = tmp_path / "image.jpg"
    img.write_bytes(b"fake-image")
    music = tmp_path / "music.mp3"
    music.write_bytes(b"fake-music")
    output = tmp_path / "out.mp4"

    processor = MediaProcessor()
    monkeypatch.setattr(processor, "_probe_duration", lambda path: 10.0)

    command, metadata = processor._build_douyin_clean_command(
        visual_paths=[str(img)],
        music=str(music),
        options=RenderOptions(image_duration=2.6, resolution="1080x1920", fps=30),
        output=str(output),
    )

    command_text = " ".join(command)
    assert metadata["music_duration_seconds"] == 10.0
    assert metadata["cycle_count"] == 1
    assert metadata["rendered_scene_count"] == 1
    assert metadata["transition"] == "none"
    assert command.count("-loop") == 1
    assert "10.000" in command
    assert "xfade=transition=wipeleft" not in command_text
    assert "flags=lanczos" in command_text


def test_douyin_clean_command_without_music_does_not_repeat_visuals(tmp_path):
    images = []
    for index in range(2):
        img = tmp_path / f"image_{index}.jpg"
        img.write_bytes(b"fake-image")
        images.append(str(img))
    output = tmp_path / "out.mp4"

    processor = MediaProcessor()

    command, metadata = processor._build_douyin_clean_command(
        visual_paths=images,
        music=None,
        options=RenderOptions(image_duration=2.6, resolution="1080x1920", fps=30),
        output=str(output),
    )

    assert metadata["music_duration_seconds"] is None
    assert metadata["cycle_count"] == 1
    assert command.count("-loop") == 2
    assert "-an" in command


@pytest.mark.asyncio
async def test_render_slideshow_uses_live_photo_command_when_live_videos_exist(tmp_path, monkeypatch):
    image = tmp_path / "live_0000_img.jpg"
    image.write_bytes(b"fake-image")
    video = tmp_path / "live_0000_vid.mp4"
    video.write_bytes(b"fake-video")
    music = tmp_path / "music.mp3"
    music.write_bytes(b"fake-music")
    output_dir = tmp_path / "out"

    processor = MediaProcessor()
    monkeypatch.setattr(processor, "_probe_duration", lambda path: 6.0)
    captured = {}

    def fake_run(cmd, timeout, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        out = output_dir / "douyin_slideshow.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-output")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)

    output = await processor.render_slideshow(
        task_id="task-live",
        image_paths=[str(image)],
        music_path=str(music),
        options=RenderOptions(image_duration=2.6, resolution="1080x1920"),
        output_dir=output_dir,
        live_photo_videos=[str(video)],
    )

    assert output.endswith("douyin_slideshow.mp4")
    command_text = " ".join(captured["cmd"])
    assert str(video) in command_text
    assert "xfade=transition=wipeleft" not in command_text
    assert "force_original_aspect_ratio=decrease" in command_text
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["errors"] == "replace"


@pytest.mark.asyncio
async def test_render_slideshow_records_render_metadata_and_logs_evidence(tmp_path, monkeypatch, caplog):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"fake-image")
    music = tmp_path / "music.mp3"
    music.write_bytes(b"fake-music")
    output_dir = tmp_path / "out"

    processor = MediaProcessor()
    processor.ffmpeg = "C:/Ptu/ffmpeg.exe"
    monkeypatch.setattr(processor, "_probe_duration", lambda path: 7.0)

    def fake_run(cmd, timeout, **kwargs):
        out = output_dir / "douyin_slideshow.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-output")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)

    with caplog.at_level(logging.INFO, logger="app.media"):
        output = await processor.render_slideshow(
            task_id="task-log",
            image_paths=[str(image)],
            music_path=str(music),
            options=RenderOptions(image_duration=2.6, resolution="1080x1920"),
            output_dir=output_dir,
        )

    assert output.endswith("douyin_slideshow.mp4")
    assert processor.last_render_metadata["output_filename"] == "douyin_slideshow.mp4"
    assert processor.last_render_metadata["music_duration_seconds"] == 7.0
    assert processor.last_render_metadata["cycle_count"] == 1
    assert processor.last_render_metadata["ffmpeg_path"] == "C:/Ptu/ffmpeg.exe"
    assert processor.last_render_metadata["transition"] == "none"
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "FFmpeg=C:/Ptu/ffmpeg.exe" in log_text
    assert "音乐=7.000s" in log_text
    assert "循环=1" in log_text


def test_media_subprocess_kwargs_hide_windows_console(monkeypatch):
    processor = MediaProcessor()
    monkeypatch.setattr("sys.platform", "win32")
    kwargs = processor._subprocess_kwargs()

    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert "creationflags" in kwargs


def test_live_photo_and_downloader_subprocesses_hide_windows_console():
    live_photo_source = __import__(
        "backend.app.services.live_photo", fromlist=["dummy"]
    ).__loader__.get_source("backend.app.services.live_photo")
    downloader_source = __import__(
        "backend.app.services.downloader", fromlist=["dummy"]
    ).__loader__.get_source("backend.app.services.downloader")

    assert "CREATE_NO_WINDOW" in live_photo_source
    assert "CREATE_NO_WINDOW" in downloader_source
    assert '"-crf", "18"' in downloader_source
