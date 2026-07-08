from __future__ import annotations

from pathlib import Path

from backend.app.js_api import _normalize_douyin_url


def test_builtin_douyin_browser_dock_is_present_and_low_risk():
    html = Path("backend/app/templates/index.html").read_text(encoding="utf-8")
    js = Path("backend/app/static/js/app.js").read_text(encoding="utf-8")

    assert 'id="browser-dock"' in html
    assert 'id="browser-native-host"' in html
    assert 'id="browser-login-panel"' in html
    assert 'data-tab="browser"' not in html
    assert 'id="tab-browser"' not in html
    assert 'id="browser-frame"' not in html
    assert 'id="login-modal"' not in html
    assert "不自动扫描页面" in html
    assert "不自动翻页" in html
    assert "手动复制链接" in html
    assert "openDouyinPanel" in js
    assert "copyBrowserUrl" not in js
    assert "useBrowserUrlAsSingle" not in js
    assert "useBrowserUrlAsProfile" not in js
    assert "mountBrowserDock" in js


def test_js_api_restricts_douyin_panel_to_douyin_hosts():
    assert _normalize_douyin_url("https://www.douyin.com/user/MS4wLjAB") == "https://www.douyin.com/user/MS4wLjAB"
    assert _normalize_douyin_url("www.douyin.com/").startswith("https://www.douyin.com/")
    assert _normalize_douyin_url("javascript:alert(1)") == "https://www.douyin.com/"
    assert _normalize_douyin_url("https://example.com/") == "https://www.douyin.com/"


def test_js_api_exposes_user_triggered_browser_bridge_only():
    source = Path("backend/app/js_api.py").read_text(encoding="utf-8")

    assert "def open_douyin_panel" in source
    assert "def mount_douyin_panel" in source
    assert "def resize_douyin_panel" in source
    assert "def sync_douyin_panel_login" in source
    assert "def clear_douyin_panel_login" in source
    assert "def hide_douyin_panel" in source
    assert "def get_douyin_panel_url" in source
    assert "def copy_douyin_panel_url" not in source
    assert "webview.create_window" not in source
    assert "NativeDouyinPanel" in source
    assert "never reads the user's Edge/Chrome profile" in source


def test_native_douyin_panel_intercepts_new_windows_inside_main_window():
    source = Path("backend/app/desktop_douyin_panel.py").read_text(encoding="utf-8")

    assert "WebView2" in source
    assert "self._form.Controls.Add(webview)" in source
    assert "self._last_rect" in source
    assert "self._form.Resize += self._on_form_layout_changed" in source
    assert "self._form.Move += self._on_form_layout_changed" in source
    assert "core.NewWindowRequested += self._on_new_window" in source
    assert "args.Handled = True" in source
    assert "self._navigate(uri, force_reload=True)" in source


def test_browser_dock_keeps_native_panel_synced_during_window_resize():
    js = Path("backend/app/static/js/app.js").read_text(encoding="utf-8")

    assert "browserDockSyncTimer" in js
    assert "window.addEventListener('resize', sync)" in js
    assert "window.visualViewport.addEventListener('resize', sync)" in js
    assert "setInterval(sync" in js


def test_first_run_disclaimer_is_present():
    html = Path("backend/app/templates/index.html").read_text(encoding="utf-8")
    js = Path("backend/app/static/js/app.js").read_text(encoding="utf-8")

    assert 'id="disclaimer-modal"' in html
    assert "Ptu 使用前说明" in html
    assert "不绕过验证码" in html
    assert "同意并进入" in html
    assert "ptu-disclaimer-accepted-v1" in js
    assert "showDisclaimerIfNeeded" in js
