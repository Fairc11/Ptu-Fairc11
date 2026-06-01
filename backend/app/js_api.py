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
from pathlib import Path


class JsApi:
    """JavaScript bridge for native desktop features."""

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

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
        try:
            subprocess.Popen(["explorer", "/select,", path])
        except Exception:
            pass

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
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                input=text or "", text=True, encoding="utf-8", check=False,
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

    def get_clipboard(self) -> str:
        # Prefer the Win32 clipboard API. It is faster and more reliable in
        # pywebview/windowless packaged mode than spawning PowerShell.
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

        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True, text=True, timeout=5
            )
            return r.stdout.strip()
        except Exception:
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
