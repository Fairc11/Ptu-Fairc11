from __future__ import annotations

import importlib
import sys


def test_find_ffmpeg_prefers_exe_directory_in_frozen_mode(tmp_path, monkeypatch):
    import backend.app.config as config

    exe_dir = tmp_path / "Ptu"
    exe_dir.mkdir()
    ffmpeg = exe_dir / "ffmpeg.exe"
    ffmpeg.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "Ptu.exe"))

    config = importlib.reload(config)

    assert config._find_ffmpeg() == str(ffmpeg)


def test_setup_check_detects_bundled_ffmpeg(tmp_path, monkeypatch):
    import setup_check

    exe_dir = tmp_path / "Ptu"
    exe_dir.mkdir()
    ffmpeg = exe_dir / "ffmpeg.exe"
    ffmpeg.write_text("", encoding="utf-8")

    monkeypatch.setattr(setup_check.sys, "frozen", True, raising=False)
    monkeypatch.setattr(setup_check.sys, "executable", str(exe_dir / "Ptu.exe"))
    monkeypatch.setenv("PTU_RUNTIME_DIR", str(tmp_path / "runtime"))

    assert setup_check.check_ffmpeg() is True


def test_build_spec_bundles_ffprobe_for_music_duration_probe():
    spec_text = open("build.spec", encoding="utf-8").read()

    assert "vendor' / 'ffmpeg' / 'ffprobe.exe" in spec_text
    assert "_copy_to_dist_root(_vendor_ffprobe)" in spec_text


def test_build_spec_copies_ffmpeg_to_exe_directory_not_internal_only():
    spec_text = open("build.spec", encoding="utf-8").read()

    assert "_copy_to_dist_root(_vendor_ffmpeg)" in spec_text
    assert "datas.append((str(_vendor_ffmpeg), '.'))" not in spec_text
