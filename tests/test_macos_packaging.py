from __future__ import annotations

from pathlib import Path


def test_macos_build_spec_is_separate_from_windows_spec():
    spec = Path("build_macos.spec")
    text = spec.read_text(encoding="utf-8")

    assert "BUNDLE(" in text
    assert "name='Ptu.app'" in text
    assert "bundle_identifier='com.fairc11.ptu'" in text
    assert "webview.platforms.cocoa" in text
    assert "webview.platforms.winforms" not in text
    assert "win32api" not in text
    assert "win32event" not in text


def test_macos_build_spec_collects_runtime_assets():
    text = Path("build_macos.spec").read_text(encoding="utf-8")

    assert "backend_dir.rglob" in text
    assert "certifi.where()" in text
    assert "f2/conf" in text
    assert "chromium_headless_shell-*" in text
    assert "chrome-headless-shell" in text
    assert "ffmpeg" in text
    assert "ffprobe" in text
    assert "THIRD_PARTY_NOTICES.md" in text


def test_macos_build_script_uses_dedicated_spec_and_checks_tools():
    script = Path("build_macos.sh")
    text = script.read_text(encoding="utf-8")

    assert "build_macos.spec" in text
    assert "-m PyInstaller" in text
    assert "PTU_MAC_FFMPEG_DIR" in text
    assert "ffmpeg" in text
    assert "ffprobe" in text
    assert "dist/Ptu.app" in text


def test_dev_requirements_include_pyinstaller_for_packaging():
    text = Path("requirements-dev.txt").read_text(encoding="utf-8")

    assert "-r backend/requirements.txt" in text
    assert "pyinstaller" in text.lower()
