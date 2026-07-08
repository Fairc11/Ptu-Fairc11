"""Windows native Douyin panel mounted inside the main pywebview window.

pywebview cannot embed an external site inside an HTML div because the main app is
already a WebView. This module mounts a second WebView2 control as a child of the
same WinForms top-level window and keeps it aligned with the right dock host.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ALLOWED_DOUYIN_HOSTS = {
    "www.douyin.com",
    "douyin.com",
    "v.douyin.com",
    "www.iesdouyin.com",
    "iesdouyin.com",
}


def _normalize_douyin_url(url: str | None) -> str:
    value = (url or "").strip()
    if not value:
        return "https://www.douyin.com/"
    if value.startswith("www."):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return "https://www.douyin.com/"
    if (parsed.netloc or "").lower() not in ALLOWED_DOUYIN_HOSTS:
        return "https://www.douyin.com/"
    return value.replace("http://", "https://", 1)


class NativeDouyinPanel:
    """Manage a child WebView2 control inside the main pywebview WinForms form."""

    def __init__(self, window: Any, storage_dir: Path):
        self.window = window
        self.storage_dir = storage_dir
        self._form = None
        self._webview = None
        self._ready = threading.Event()
        self._current_url = "https://www.douyin.com/"
        self._visible = False
        self._last_rect: dict[str, float] | None = None
        self._form_events_bound = False

    @property
    def available(self) -> bool:
        return sys.platform.startswith("win") and self.window is not None

    def mount(self, rect: dict | None = None, *, visible: bool | None = None) -> dict:
        if not self.available:
            return {"status": "missing", "message": "native panel is Windows-only"}
        try:
            self._ensure_control()
            if rect:
                self.set_bounds(rect)
            if visible is not None:
                self.set_visible(visible)
            return {"status": "ok", "visible": self._visible, "url": self._current_url}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "url": self._current_url}

    def open(self, url: str = "", rect: dict | None = None, *, force_reload: bool = True) -> dict:
        safe_url = _normalize_douyin_url(url)
        try:
            self._ensure_control()
            if rect:
                self.set_bounds(rect)
            self.set_visible(True)
            self._navigate(safe_url, force_reload=force_reload)
            return {"status": "ok", "url": safe_url}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "url": safe_url}

    def hide(self) -> dict:
        try:
            self.set_visible(False)
            return {"status": "ok", "url": self._current_url}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "url": self._current_url}

    def current_url(self) -> dict:
        return {"status": "ok" if self._webview else "missing", "url": self._current_url}

    def clear_cookies(self) -> dict:
        try:
            self._ensure_control()

            def _clear():
                if self._webview and self._webview.CoreWebView2:
                    self._webview.CoreWebView2.CookieManager.DeleteAllCookies()

            self._invoke(_clear)
            self._navigate("https://www.douyin.com/", force_reload=True)
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def sync_cookies(self, cookies: dict[str, str], url: str = "") -> dict:
        safe_url = _normalize_douyin_url(url)
        if not cookies:
            return {"status": "missing_cookies", "url": safe_url, "synced": 0}
        try:
            self._ensure_control()

            def _sync():
                manager = self._webview.CoreWebView2.CookieManager
                for name, value in cookies.items():
                    cookie = manager.CreateCookie(name, value, ".douyin.com", "/")
                    cookie.IsSecure = True
                    manager.AddOrUpdateCookie(cookie)

            self._invoke(_sync)
            self.set_visible(True)
            self._navigate(safe_url, force_reload=True)
            return {"status": "ok", "url": safe_url, "synced": len(cookies)}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "url": safe_url, "synced": 0}

    def set_bounds(self, rect: dict) -> dict:
        self._ensure_control()
        x = float(rect.get("x") or 0)
        y = float(rect.get("y") or 0)
        width = max(1, float(rect.get("width") or 1))
        height = max(1, float(rect.get("height") or 1))
        self._last_rect = {"x": x, "y": y, "width": width, "height": height}

        def _set():
            self._apply_bounds(self._last_rect)

        self._invoke(_set)
        return {"status": "ok"}

    def set_visible(self, visible: bool) -> dict:
        self._ensure_control()

        def _show_hide():
            self._webview.Visible = bool(visible)
            if visible:
                self._webview.BringToFront()

        self._invoke(_show_hide)
        self._visible = bool(visible)
        return {"status": "ok", "visible": self._visible}

    def _ensure_control(self) -> None:
        if self._webview is not None:
            return
        if not self.window or not getattr(self.window, "native", None):
            raise RuntimeError("main native window is not ready")

        self._form = self.window.native
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        def _create():
            import clr
            from webview.util import interop_dll_path

            clr.AddReference("System.Windows.Forms")
            clr.AddReference(interop_dll_path("Microsoft.Web.WebView2.Core.dll"))
            clr.AddReference(interop_dll_path("Microsoft.Web.WebView2.WinForms.dll"))

            for platform in ("win-arm64", "win-x64", "win-x86"):
                os.environ["Path"] += ";" + interop_dll_path(platform)

            from System import Uri
            from System.Drawing import Color
            from Microsoft.Web.WebView2.WinForms import CoreWebView2CreationProperties, WebView2

            webview = WebView2()
            props = CoreWebView2CreationProperties()
            props.UserDataFolder = str(self.storage_dir)
            props.AdditionalBrowserArguments = "--disable-features=ElasticOverscroll"
            webview.CreationProperties = props
            webview.Visible = False
            webview.DefaultBackgroundColor = Color.FromArgb(255, 18, 18, 18)
            self._form.Controls.Add(webview)
            webview.BringToFront()
            self._webview = webview
            self._bind_form_events()

            def _ready(sender, args):
                if not args.IsSuccess:
                    self._ready.set()
                    return
                core = sender.CoreWebView2
                core.NewWindowRequested += self._on_new_window
                core.SourceChanged += self._on_source_changed
                core.NavigationStarting += self._on_navigation_starting
                settings = core.Settings
                settings.AreDefaultContextMenusEnabled = False
                settings.AreDevToolsEnabled = False
                settings.IsStatusBarEnabled = False
                settings.IsSwipeNavigationEnabled = False
                settings.IsZoomControlEnabled = True
                self._ready.set()
                sender.Source = Uri(self._current_url)

            webview.CoreWebView2InitializationCompleted += _ready
            webview.EnsureCoreWebView2Async(None)

        self._invoke(_create)
        self._ready.wait(20)

    def _bind_form_events(self) -> None:
        if self._form_events_bound or self._form is None:
            return
        self._form.Resize += self._on_form_layout_changed
        self._form.SizeChanged += self._on_form_layout_changed
        self._form.Move += self._on_form_layout_changed
        self._form_events_bound = True

    def _apply_bounds(self, rect: dict[str, float] | None) -> None:
        if not rect or self._webview is None or self._form is None:
            return
        scale = float(getattr(self._form, "_scale", 1.0) or 1.0)
        self._webview.Left = int(float(rect.get("x") or 0) * scale)
        self._webview.Top = int(float(rect.get("y") or 0) * scale)
        self._webview.Width = max(1, int(float(rect.get("width") or 1) * scale))
        self._webview.Height = max(1, int(float(rect.get("height") or 1) * scale))
        if self._visible:
            self._webview.BringToFront()

    def _navigate(self, url: str, *, force_reload: bool) -> None:
        safe_url = _normalize_douyin_url(url)
        self._ensure_control()

        def _load():
            from System import Uri
            if force_reload and self._webview.CoreWebView2:
                self._webview.CoreWebView2.Navigate("about:blank")
            self._webview.Source = Uri(safe_url)
            self._current_url = safe_url

        self._invoke(_load)

    def _invoke(self, func):
        try:
            import clr  # noqa: F401
        except Exception:
            os.environ["PYTHONNET_RUNTIME"] = "coreclr"
            import clr  # noqa: F401
        from System import Func, Type

        if self._form is None:
            self._form = self.window.native
        if self._form.InvokeRequired:
            return self._form.Invoke(Func[Type](func))
        return func()

    def _on_form_layout_changed(self, _sender, _args):
        try:
            if self._visible and self._last_rect:
                self._apply_bounds(self._last_rect)
        except Exception:
            pass

    def _on_source_changed(self, sender, _args):
        try:
            self._current_url = str(sender.Source)
        except Exception:
            pass

    def _on_new_window(self, _sender, args):
        args.Handled = True
        uri = str(args.Uri or "")
        self._navigate(uri, force_reload=True)

    def _on_navigation_starting(self, _sender, args):
        uri = str(args.Uri or "")
        if not _is_allowed_douyin_uri(uri):
            args.Cancel = True
            self._navigate("https://www.douyin.com/", force_reload=True)


def _is_allowed_douyin_uri(uri: str) -> bool:
    if uri == "about:blank":
        return True
    try:
        parsed = urlparse(uri)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.netloc.lower() in ALLOWED_DOUYIN_HOSTS
