from __future__ import annotations

import importlib
from pathlib import Path


def test_get_chromium_path_detects_direct_downloaded_headless_shell(tmp_path, monkeypatch):
    import setup_check

    setup_check = importlib.reload(setup_check)
    browser_dir = tmp_path / "ms-playwright"
    exe = (
        browser_dir
        / "chromium_headless_shell-1217"
        / "chrome-headless-shell-win64"
        / "headless_shell.exe"
    )
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(setup_check, "_get_playwright_browsers_dir", lambda: browser_dir)

    assert setup_check.get_chromium_path() == str(exe)
    assert setup_check.check_playwright() is True


def test_get_chromium_path_detects_playwright_chrome(tmp_path, monkeypatch):
    import setup_check

    setup_check = importlib.reload(setup_check)
    browser_dir = tmp_path / "ms-playwright"
    exe = browser_dir / "chromium-1217" / "chrome-win64" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(setup_check, "_get_playwright_browsers_dir", lambda: browser_dir)

    assert setup_check.get_chromium_path() == str(exe)

