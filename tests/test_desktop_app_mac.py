from __future__ import annotations

import subprocess

import desktop_app
from backend.app.js_api import JsApi


def test_webview_start_kwargs_omit_tuple_menu_on_macos(monkeypatch):
    monkeypatch.setattr(desktop_app.sys, "platform", "darwin")

    app = desktop_app.DesktopApp()
    kwargs = app._webview_start_kwargs([("显示", lambda: None)])

    assert "menu" not in kwargs
    assert kwargs["storage_path"].endswith(".ptu")


def test_webview_start_kwargs_keep_menu_on_windows(monkeypatch):
    monkeypatch.setattr(desktop_app.sys, "platform", "win32")

    app = desktop_app.DesktopApp()
    menu = [("显示", lambda: None)]
    kwargs = app._webview_start_kwargs(menu)

    assert kwargs["menu"] == menu


def test_desktop_platform_label_matches_macos(monkeypatch):
    monkeypatch.setattr(desktop_app.sys, "platform", "darwin")

    assert desktop_app._desktop_platform_label() == "Mac 桌面客户端"


def test_mac_douyin_panel_returns_structured_unsupported(monkeypatch):
    import backend.app.js_api as js_api

    monkeypatch.setattr(js_api.sys, "platform", "darwin")
    api = JsApi()

    result = api.open_douyin_panel("https://www.douyin.com/user/test")

    assert result["status"] == "unsupported"
    assert "Mac" in result["message"]
    assert result["url"] == "https://www.douyin.com/user/test"


def test_open_external_douyin_url_uses_macos_open(monkeypatch):
    import backend.app.js_api as js_api

    calls = []

    monkeypatch.setattr(js_api.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(args))

    result = JsApi().open_external_url("https://www.douyin.com/user/test")

    assert result == {"status": "ok", "url": "https://www.douyin.com/user/test"}
    assert calls == [["open", "https://www.douyin.com/user/test"]]


def test_open_external_douyin_url_keeps_host_restriction(monkeypatch):
    import backend.app.js_api as js_api

    calls = []

    monkeypatch.setattr(js_api.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(args))

    result = JsApi().open_external_url("https://example.com/")

    assert result == {"status": "ok", "url": "https://www.douyin.com/"}
    assert calls == [["open", "https://www.douyin.com/"]]


def test_open_in_explorer_uses_macos_open_for_directory(monkeypatch, tmp_path):
    import backend.app.js_api as js_api

    calls = []

    monkeypatch.setattr(js_api.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(args))

    result = JsApi().open_in_explorer(str(tmp_path))

    assert result == {"status": "ok", "path": str(tmp_path)}
    assert calls == [["open", str(tmp_path)]]


def test_set_clipboard_uses_pbcopy_on_macos(monkeypatch):
    import backend.app.js_api as js_api

    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(js_api.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", fake_run)

    JsApi().set_clipboard("abc")

    assert calls == [
        (
            ["pbcopy"],
            {
                "input": "abc",
                "text": True,
                "encoding": "utf-8",
                "check": False,
                "capture_output": True,
                "timeout": 5,
            },
        )
    ]


def test_frozen_macos_window_state_uses_application_support(monkeypatch):
    monkeypatch.setattr(desktop_app.sys, "platform", "darwin")
    monkeypatch.setattr(desktop_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop_app.sys, "executable", "/Applications/Ptu.app/Contents/MacOS/Ptu")

    state_file = desktop_app._window_state_file()

    assert state_file == desktop_app.Path.home() / "Library" / "Application Support" / "Ptu" / "ptu_window_state.json"
