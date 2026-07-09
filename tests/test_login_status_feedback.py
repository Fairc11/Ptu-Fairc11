from __future__ import annotations

from pathlib import Path
import time

import pytest

from backend.app.services.scraper import DouyinScraper
from backend.app.services.qr_login import QRLoginService, _default_playwright_browsers_path, _hidden_browser_args


def test_qr_login_status_mapping_is_user_visible(tmp_path):
    service = QRLoginService(cookies_path=tmp_path / "cookies.yaml")

    assert service._normalize_qr_status({"status": "2"}) == "scanned"
    assert service._normalize_qr_status({"status": "3"}) == "done"
    assert service._normalize_qr_status({"message": "二维码已过期"}) == "expired"
    assert service._status_message("scanned") == "已扫码，请在手机上确认登录"


def test_login_modal_handles_scanned_expired_and_errors():
    js = Path("backend/app/static/js/app.js").read_text(encoding="utf-8")

    assert "已扫码，请在手机上确认登录" in js
    assert "二维码已过期，请刷新" in js
    assert "网络异常，请稍后重试" in js
    poll_start = js.index("poll()")
    poll_end = js.index("// ── Lightbox", poll_start)
    assert "catch(() => {})" not in js[poll_start:poll_end]


def test_startup_does_not_auto_open_qr_modal():
    html = Path("backend/app/templates/base.html").read_text(encoding="utf-8")

    assert "Ptu.ui.loginModal.open()" not in html


def test_scraper_does_not_read_user_browser_profile_for_cookies(tmp_path, monkeypatch):
    called = {"browser": False}
    scraper = DouyinScraper(cookies_path=str(tmp_path / "cookies.yaml"))

    def fake_browser_loader():
        called["browser"] = True

    monkeypatch.setattr(scraper, "_load_cookies_from_browser", fake_browser_loader, raising=False)

    scraper._load_cookies(scraper._cookies_path)

    assert called["browser"] is False


def test_qr_browser_fallback_is_forced_hidden():
    args = _hidden_browser_args()

    assert "--headless=new" in args
    assert "--window-position=-32000,-32000" in args
    assert "--window-size=1,1" in args


def test_qr_playwright_default_browser_path_is_platform_specific(monkeypatch):
    import backend.app.services.qr_login as qr_login

    monkeypatch.setattr(qr_login.sys, "platform", "darwin")
    mac_path = _default_playwright_browsers_path()

    monkeypatch.setattr(qr_login.sys, "platform", "win32")
    win_path = _default_playwright_browsers_path()

    assert mac_path == Path.home() / "Library" / "Caches" / "ms-playwright"
    assert win_path == Path.home() / "AppData" / "Local" / "ms-playwright"


@pytest.mark.asyncio
async def test_qr_api_failure_cache_skips_slow_direct_retry(tmp_path, monkeypatch):
    service = QRLoginService(cookies_path=tmp_path / "cookies.yaml")
    service._api_disabled_until = time.time() + 60
    called = {"api": False}

    async def fake_api():
        called["api"] = True
        raise AssertionError("direct API should be skipped")

    async def fake_pw(executable_path=None):
        return {"qrcode": "fake", "token": "qr", "expires_in": 120}

    monkeypatch.setattr(service, "_get_qrcode_api", fake_api)
    monkeypatch.setattr(service, "_get_qrcode_pw", fake_pw)
    monkeypatch.setattr("backend.app.services.qr_login._find_chromium", lambda: "chromium.exe")

    assert await service.get_qrcode() == {"qrcode": "fake", "token": "qr", "expires_in": 120}
    assert called["api"] is False


@pytest.mark.asyncio
async def test_qr_browser_fallback_uses_bundled_chromium_not_system_edge(tmp_path, monkeypatch):
    service = QRLoginService(cookies_path=tmp_path / "cookies.yaml")
    calls = []

    async def fake_api():
        raise RuntimeError("API返回非JSON: status=403, body=路由已封禁")

    async def fake_pw(channel=None, executable_path=None):
        calls.append({"channel": channel, "executable_path": executable_path})
        return {"qrcode": "bundled", "token": "qr", "expires_in": 120}

    monkeypatch.setattr(service, "_get_qrcode_api", fake_api)
    monkeypatch.setattr(service, "_get_qrcode_pw", fake_pw)
    monkeypatch.setattr("backend.app.services.qr_login._find_chromium", lambda: "chrome-headless-shell.exe")

    result = await service.get_qrcode()

    assert result["qrcode"] == "bundled"
    assert calls == [{"channel": None, "executable_path": "chrome-headless-shell.exe"}]
