#!/usr/bin/env python3
"""
Ptu - Windows 桌面客户端
"""
from __future__ import annotations
import os
import sys
import json
import socket
import threading
from pathlib import Path

# 单实例锁
try:
    import win32event, win32api
    from backend.app.version import VERSION
    mutex_name = f"Ptu-Desktop-{VERSION}"
    mutex = win32event.CreateMutex(None, False, mutex_name)
    if win32api.GetLastError() == 183:
        print("[Ptu] 程序已在运行")
        sys.exit(0)
except ImportError:
    pass

backend_dir = Path(__file__).parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if sys.stdout and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if getattr(sys, 'frozen', False):
    STATE_FILE = Path(sys.executable).parent / ".ptu_window_state.json"
else:
    STATE_FILE = Path(__file__).parent / ".ptu_window_state.json"


def _load_window_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text("utf-8"))
    except Exception:
        pass
    return {"w": 1200, "h": 800, "x": None, "y": None, "maximized": False}


def _save_window_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), "utf-8")
    except Exception:
        pass


def find_free_port(start: int = 18080, end: int = 18180) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


class DesktopApp:
    """pywebview 桌面窗口管理器."""

    def __init__(self):
        self.host = "127.0.0.1"
        self.port = find_free_port()
        self.server_thread: threading.Thread | None = None
        self.ready_event = threading.Event()
        self.window = None
        self.js_api = None
        self.app_exiting = False
        self.window_state = _load_window_state()

    def _init_js_api(self):
        from backend.app.js_api import JsApi
        self.js_api = JsApi()

    def _start_server(self):
        """后台启动 FastAPI 服务器."""
        import uvicorn
        import backend.app.config as cfg
        cfg.settings.port = self.port
        cfg.settings.host = self.host
        from backend.app.main import app

        # 热重载仅开发模式启用（封包后 reload 会导致频繁重启，破坏 Playwright 会话）
        is_dev = not getattr(sys, 'frozen', False)
        base = Path(__file__).parent
        backend_path = str(base / "backend")
        config = uvicorn.Config(
            app, host=self.host, port=self.port,
            log_level="warning",
            reload=is_dev,
            reload_dirs=[backend_path] if is_dev else None,
            reload_includes=["*.py", "*.html", "*.css", "*.js"] if is_dev else None,
        )
        server = uvicorn.Server(config)
        self.ready_event.set()
        try:
            server.run()
        except Exception as e:
            print(f"[服务器] 错误: {e}")

    def _save_current_window_state(self):
        """保存窗口位置和尺寸。"""
        try:
            x, y = self.window.x, self.window.y
            w, h = self.window.width, self.window.height
            _save_window_state({
                "w": w, "h": h, "x": x, "y": y,
                "maximized": False,
            })
        except Exception:
            pass

    def _on_restore(self):
        """从托盘恢复."""
        try:
            self.window.show()
            self.window.restore()
        except Exception:
            pass

    def run(self):
        import webview
        import time as _time
        _t0 = _time.time()

        self._init_js_api()

        # 启动服务器
        print(f"[桌面客户端] 启动服务器 (端口 {self.port})... [t={_time.time()-_t0:.2f}s]")
        self.server_thread = threading.Thread(
            target=self._start_server, daemon=True
        )
        self.server_thread.start()

        if not self.ready_event.wait(timeout=15):
            print("[桌面客户端] 服务器启动超时!")
            return

        print(f"[桌面客户端] 服务器就绪 [t={_time.time()-_t0:.2f}s]")
        server_url = f"http://{self.host}:{self.port}/"
        ws = self.window_state

        # 托盘菜单
        def tray_show():
            self._on_restore()
        def tray_quit():
            self.app_exiting = True
            try:
                self.window.destroy()
            except Exception:
                pass
            # 强制退出
            import os
            os._exit(0)

        tray_menu = [
            ("显示", tray_show),
            ("退出", tray_quit),
        ]

        # 创建窗口
        self.window = webview.create_window(
            title="Ptu",
            url=server_url,
            width=ws.get("w", 1200),
            height=ws.get("h", 800),
            x=ws.get("x"),
            y=ws.get("y"),
            min_size=(860, 580),
            frameless=False,
            easy_drag=True,
            resizable=True,
            fullscreen=False,
            maximized=ws.get("maximized", False),
            text_select=True,
            confirm_close=False,
            js_api=self.js_api,
        )

        if self.js_api:
            self.js_api.set_window(self.window)

        # 启动时清除 pywebview 静态文件缓存（开发模式）
        cache_dir = Path.home() / ".ptu"
        try:
            import shutil
            for sub in ["Cache", "Code Cache", "GPUCache"]:
                p = cache_dir / "Default" / sub
                if p.exists():
                    shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass

        webview.start(
            debug=False,
            http_server=False,
            private_mode=False,
            storage_path=str(cache_dir),
            menu=tray_menu,
        )

        # 窗口关闭后保存状态
        self._save_current_window_state()
        print("[桌面客户端] 已退出")


def main():
    print("=" * 50)
    from backend.app.version import VERSION
    print(f"  {VERSION} - Windows 桌面客户端")
    print("=" * 50)
    print()

    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    main()
