"""
JS API for pywebview native features.
Exposes Python functions to the web frontend for native Windows
functionality like file save dialogs, window management, and notifications.
"""
from __future__ import annotations
import os
import sys
import ctypes
import subprocess
import json
import time
from pathlib import Path
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
    host = (parsed.netloc or "").lower()
    if host not in ALLOWED_DOUYIN_HOSTS:
        return "https://www.douyin.com/"
    return value.replace("http://", "https://", 1)


DOUYIN_COOKIE_NAMES = (
    "sessionid",
    "sid_tt",
    "sid_guard",
    "passport_csrf_token",
    "msToken",
    "ttwid",
    "odin_tt",
)


def _load_ptu_douyin_cookies() -> dict[str, str]:
    try:
        import yaml
        from .config import settings

        path = Path(settings.cookies_path)
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text("utf-8")) or {}
        return {
            name: str(data.get(name) or "")
            for name in DOUYIN_COOKIE_NAMES
            if data.get(name)
        }
    except Exception:
        return {}


def _cookie_sync_script(cookies: dict[str, str], *, clear: bool = False) -> str:
    if clear:
        payload = {name: "" for name in DOUYIN_COOKIE_NAMES}
        max_age = 0
    else:
        payload = cookies
        max_age = 60 * 60 * 24 * 30
    return f"""
        (function() {{
            const cookies = {json.dumps(payload, ensure_ascii=False)};
            for (const [name, value] of Object.entries(cookies)) {{
                const encoded = encodeURIComponent(value || '');
                document.cookie = `${{name}}=${{encoded}}; Domain=.douyin.com; Path=/; Max-Age={max_age}; Secure; SameSite=None`;
            }}
            return Object.keys(cookies).length;
        }})();
    """


class JsApi:
    """JavaScript bridge for native desktop features."""

    def __init__(self):
        self._window = None
        self._douyin_panel = None

    def set_window(self, window):
        self._window = window
        self._douyin_panel = None

    # ── File Dialogs ───────────────────────────────────────────────────

    def save_file_dialog(self, title: str = "保存文件",
                         file_types: tuple = ("MP4 Video", "*.mp4"),
                         default_name: str = "slideshow.mp4") -> str | None:
        try:
            if self._window:
                result = self._window.create_file_dialog(
                    dialog_type=2, title=title,
                    file_types=[file_types],
                )
                if result:
                    return result
        except Exception:
            pass
        return None

    def open_file_dialog(self, title: str = "选择文件",
                         file_types: tuple = ("All Files", "*.*")) -> list[str]:
        try:
            if self._window:
                result = self._window.create_file_dialog(
                    dialog_type=1, title=title,
                    file_types=[file_types],
                    allow_multiple=True,
                )
                if result:
                    return result
        except Exception:
            pass
        return []

    # ── Notifications ──────────────────────────────────────────────────

    def show_notification(self, title: str, message: str):
        try:
            from plyer import notification
            notification.notify(title=title, message=message,
                                app_name="Ptu", timeout=5)
        except Exception:
            pass

    # ── Path Helpers ───────────────────────────────────────────────────

    def get_app_path(self) -> str:
        if getattr(sys, 'frozen', False):
            return str(Path(sys.executable).parent)
        return str(Path(__file__).parent.parent.parent)

    def get_downloads_path(self) -> str:
        try:
            CSIDL_PERSONAL = 5
            SHGFP_TYPE_CURRENT = 0
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(
                None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf
            )
            return buf.value
        except Exception:
            return os.path.expanduser("~/Downloads")

    def open_in_explorer(self, path: str):
        target = Path(path)
        try:
            if sys.platform == "darwin":
                args = ["open", "-R", str(target)] if target.is_file() else ["open", str(target)]
            elif sys.platform.startswith("win"):
                args = ["explorer", "/select,", str(target)] if target.is_file() else ["explorer", str(target)]
            else:
                folder = target.parent if target.is_file() else target
                args = ["xdg-open", str(folder)]
            subprocess.Popen(args)
            return {"status": "ok", "path": str(target)}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "path": str(target)}

    def open_external_url(self, url: str = "") -> dict:
        safe_url = _normalize_douyin_url(url)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", safe_url])
            elif sys.platform.startswith("win"):
                os.startfile(safe_url)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", safe_url])
            return {"status": "ok", "url": safe_url}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "url": safe_url}

    # ── Built-in Douyin Browser Panel ─────────────────────────────────

    def _native_douyin_panel_supported(self) -> bool:
        return sys.platform.startswith("win")

    def _unsupported_douyin_panel_result(self, url: str = "", **extra) -> dict:
        result = {
            "status": "unsupported",
            "message": "Mac V1.5 版暂不支持内嵌抖音预览，请在系统浏览器复制链接后粘贴到左侧。",
            "url": _normalize_douyin_url(url),
        }
        result.update(extra)
        return result

    def _get_douyin_panel(self):
        if self._douyin_panel is None:
            from .desktop_douyin_panel import NativeDouyinPanel
            storage = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Ptu" / "DouyinPanel"
            self._douyin_panel = NativeDouyinPanel(self._window, storage)
        return self._douyin_panel

    def mount_douyin_panel(self, rect: dict | None = None, visible: bool = False) -> dict:
        """Mount the native Douyin WebView2 child control inside the main window."""
        if not self._native_douyin_panel_supported():
            return self._unsupported_douyin_panel_result()
        try:
            return self._get_douyin_panel().mount(rect, visible=visible)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def resize_douyin_panel(self, rect: dict) -> dict:
        """Keep the native child WebView aligned to the HTML dock host."""
        if not self._native_douyin_panel_supported():
            return self._unsupported_douyin_panel_result()
        try:
            return self._get_douyin_panel().set_bounds(rect)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def open_douyin_panel(self, url: str = "", rect: dict | None = None) -> dict:
        """Open Douyin in the right-dock native child WebView2 control."""
        if not self._native_douyin_panel_supported():
            return self._unsupported_douyin_panel_result(url)
        try:
            return self._get_douyin_panel().open(url, rect, force_reload=True)
        except Exception as exc:
            return {"status": "error", "message": str(exc), "url": _normalize_douyin_url(url)}

    def hide_douyin_panel(self) -> dict:
        """Hide the visible Douyin companion panel without clearing login state."""
        if not self._native_douyin_panel_supported():
            return self._unsupported_douyin_panel_result()
        try:
            return self._get_douyin_panel().hide()
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def sync_douyin_panel_login(self, url: str = "") -> dict:
        """Sync Ptu's own Douyin cookies into the visible panel session.

        This only uses cookies saved by Ptu's QR login. It never reads the user's Edge/Chrome profile,
        passwords, history, or browser cookies.
        """
        safe_url = _normalize_douyin_url(url)
        if not self._native_douyin_panel_supported():
            return self._unsupported_douyin_panel_result(safe_url, synced=0)
        cookies = _load_ptu_douyin_cookies()
        if not cookies:
            return {"status": "missing_cookies", "url": safe_url, "synced": 0}
        try:
            return self._get_douyin_panel().sync_cookies(cookies, safe_url)
        except Exception as exc:
            return {"status": "error", "message": str(exc), "url": safe_url, "synced": 0}

    def clear_douyin_panel_login(self) -> dict:
        """Clear Douyin cookies from the companion panel only."""
        if not self._native_douyin_panel_supported():
            return self._unsupported_douyin_panel_result()
        try:
            return self._get_douyin_panel().clear_cookies()
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def get_douyin_panel_url(self) -> dict:
        """Return the visible Douyin panel URL only after user request."""
        if not self._native_douyin_panel_supported():
            result = self._unsupported_douyin_panel_result()
            result["url"] = ""
            return result
        try:
            return self._get_douyin_panel().current_url()
        except Exception as exc:
            return {"status": "error", "message": str(exc), "url": ""}

    # ── Window Management ──────────────────────────────────────────────

    def minimize_window(self):
        if self._window:
            try:
                self._window.minimize()
            except Exception:
                pass

    def maximize_window(self):
        if self._window:
            try:
                self._window.maximize()
            except Exception:
                pass

    def restore_window(self):
        if self._window:
            try:
                self._window.restore()
            except Exception:
                pass

    def close_window(self):
        """关闭窗口并退出应用。"""
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass

    def is_maximized(self) -> bool:
        if self._window:
            try:
                return bool(getattr(self._window, "maximized", False))
            except Exception:
                pass
        return False

    # ── Title Bar Drag ─────────────────────────────────────────────────

    def start_titlebar_drag(self):
        """Initiate window drag from custom title bar (Windows)."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            ctypes.windll.user32.ReleaseCapture()
            ctypes.windll.user32.SendMessageW(hwnd, 0xA1, 2, 0)
        except Exception:
            pass

    # ── Clipboard ──────────────────────────────────────────────────────

    def set_clipboard(self, text: str):
        try:
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            data = (text or "") + "\0"
            byte_count = len(data.encode("utf-16-le"))
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, byte_count)
            if handle and user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    kernel32.GlobalLock.restype = ctypes.c_void_p
                    ptr = kernel32.GlobalLock(handle)
                    if ptr:
                        try:
                            ctypes.memmove(ptr, data.encode("utf-16-le"), byte_count)
                        finally:
                            kernel32.GlobalUnlock(handle)
                        user32.SetClipboardData(CF_UNICODETEXT, handle)
                        handle = None
                        return
                finally:
                    user32.CloseClipboard()
            if handle:
                kernel32.GlobalFree(handle)
        except Exception:
            pass

        try:
            kwargs = {
                "input": text or "",
                "text": True,
                "encoding": "utf-8",
                "check": False,
                "capture_output": True,
                "timeout": 5,
            }
            if sys.platform == "darwin":
                command = ["pbcopy"]
            elif sys.platform.startswith("win"):
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                command = ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"]
            else:
                command = ["xclip", "-selection", "clipboard"]
            subprocess.run(
                command,
                **kwargs,
            )
        except Exception:
            pass

    def get_clipboard(self) -> str:
        try:
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(None):
                try:
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if handle:
                        kernel32.GlobalLock.restype = ctypes.c_void_p
                        ptr = kernel32.GlobalLock(handle)
                        if ptr:
                            try:
                                text = ctypes.wstring_at(ptr)
                                if text:
                                    return text.strip()
                            finally:
                                kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass
        return ""

    # ── System Info ────────────────────────────────────────────────────

    def get_system_info(self) -> dict:
        try:
            user32 = ctypes.windll.user32
            return {
                "os": sys.platform,
                "screen_width": user32.GetSystemMetrics(0),
                "screen_height": user32.GetSystemMetrics(1),
            }
        except Exception:
            return {"os": sys.platform, "screen_width": 0, "screen_height": 0}
