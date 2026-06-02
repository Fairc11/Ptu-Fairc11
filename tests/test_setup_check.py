from __future__ import annotations

import importlib
import zipfile
from pathlib import Path


def test_get_chromium_path_detects_direct_downloaded_headless_shell(tmp_path, monkeypatch):
    import setup_check

    setup_check = importlib.reload(setup_check)
    browser_dir = tmp_path / "ms-playwright"
    exe = (
        browser_dir
        / "chromium_headless_shell-1217"
        / "chrome-headless-shell-win64"
        / "chrome-headless-shell.exe"
    )
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(setup_check, "_get_playwright_browsers_dirs", lambda: [browser_dir])

    assert setup_check.get_chromium_path() == str(exe)
    assert setup_check.check_playwright() is True


def test_get_chromium_path_detects_playwright_chrome(tmp_path, monkeypatch):
    import setup_check

    setup_check = importlib.reload(setup_check)
    browser_dir = tmp_path / "ms-playwright"
    exe = browser_dir / "chromium-1217" / "chrome-win64" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(setup_check, "_get_playwright_browsers_dirs", lambda: [browser_dir])

    assert setup_check.get_chromium_path() == str(exe)


def test_get_chromium_path_prefers_bundled_headless_shell(tmp_path, monkeypatch):
    import setup_check

    setup_check = importlib.reload(setup_check)
    bundled_dir = tmp_path / "bundle" / "ms-playwright"
    user_dir = tmp_path / "user" / "ms-playwright"
    bundled_exe = (
        bundled_dir
        / "chromium_headless_shell-1217"
        / "chrome-headless-shell-win64"
        / "chrome-headless-shell.exe"
    )
    user_exe = user_dir / "chromium-1217" / "chrome-win64" / "chrome.exe"
    bundled_exe.parent.mkdir(parents=True)
    user_exe.parent.mkdir(parents=True)
    bundled_exe.write_text("", encoding="utf-8")
    user_exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(setup_check, "_get_playwright_browsers_dirs", lambda: [bundled_dir, user_dir])

    assert setup_check.get_chromium_path() == str(bundled_exe)


def test_chromium_download_urls_use_playwright_cft_format(monkeypatch):
    import setup_check

    setup_check = importlib.reload(setup_check)
    monkeypatch.delenv("PLAYWRIGHT_DOWNLOAD_HOST", raising=False)

    urls = setup_check._get_chromium_download_urls("147.0.7727.15", "1217")

    assert urls[0] == (
        "https://cdn.playwright.dev/builds/cft/"
        "147.0.7727.15/win64/chrome-headless-shell-win64.zip"
    )
    assert "azureedge" in urls[-1]


def test_chromium_download_urls_respect_custom_host(monkeypatch):
    import setup_check

    setup_check = importlib.reload(setup_check)
    monkeypatch.setenv("PLAYWRIGHT_DOWNLOAD_HOST", "https://mirror.example.test/")

    assert setup_check._get_chromium_download_urls("147.0.7727.15", "1217") == [
        "https://mirror.example.test/builds/cft/147.0.7727.15/win64/chrome-headless-shell-win64.zip"
    ]


def test_extract_zip_strips_common_root_and_keeps_nested_files(tmp_path):
    import setup_check

    setup_check = importlib.reload(setup_check)
    archive = tmp_path / "browser.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("chrome-headless-shell-win64/chrome-headless-shell.exe", "exe")
        zf.writestr("chrome-headless-shell-win64/locales/zh-CN.pak", "pak")
        zf.writestr("chrome-headless-shell-win64/resources/info.txt", "txt")

    dest = tmp_path / "dest"
    with zipfile.ZipFile(archive) as zf:
        setup_check._extract_zip_stripping_root(zf, dest)

    assert (dest / "chrome-headless-shell.exe").read_text(encoding="utf-8") == "exe"
    assert (dest / "locales" / "zh-CN.pak").read_text(encoding="utf-8") == "pak"
    assert (dest / "resources" / "info.txt").read_text(encoding="utf-8") == "txt"
