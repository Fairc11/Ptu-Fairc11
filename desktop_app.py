#!/usr/bin/env python3
"""
Ptu v1.1.0 - Windows 桌面客户端

功能:
  - 原生 Windows 窗口 (WebView2)，无边框自定义标题栏
  - 桌面模式是默认入口，不弹浏览器
  - 关闭窗口 → 最小化到系统托盘（不退出）
  - 系统托盘右键菜单：显示/退出
  - 单实例运行
  - 窗口位置/大小记忆
  - 原生文件保存/打开对话框
  - 系统通知
  - 自动选择可用端口
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
    mutex = win32event.CreateMutex(None, False, "Ptu-Desktop-1.1.0")
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
        config = uvicorn.Config(
            app, host=self.host, port=self.port,
            log_level="warning", reload=False,
        )
        server = uvicorn.Server(config)
        self.ready_event.set()
        try:
            server.run()
        except Exception as e:
            print(f"[服务器] 错误: {e}")

    def _on_closing(self):
        """关闭窗口时保存状态并最小化到托盘，不退出。"""
        if self.app_exiting:
            return  # 真正退出，允许关闭
        try:
            x, y = self.window.x, self.window.y
            w, h = self.window.width, self.window.height
            _save_window_state({
                "w": w, "h": h, "x": x, "y": y,
                "maximized": getattr(self.window, "fullscreen", False),
            })
        except Exception:
            pass
        # 最小化到托盘
        try:
            self.window.hide()
        except Exception:
            pass
        return  # 阻止关闭，只隐藏

    def _on_restore(self):
        """从托盘恢复."""
        try:
            self.window.show()
            self.window.restore()
        except Exception:
            pass

    def run(self):
        import webview

        self._init_js_api()

        # 启动服务器
        print(f"[桌面客户端] 启动服务器 (端口 {self.port})...")
        self.server_thread = threading.Thread(
            target=self._start_server, daemon=True
        )
        self.server_thread.start()

        if not self.ready_event.wait(timeout=15):
            print("[桌面客户端] 服务器启动超时!")
            return

        server_url = f"http://{self.host}:{self.port}/?desktop=1"
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
            frameless=True,
            easy_drag=False,
            resizable=True,
            fullscreen=False,
            text_select=True,
            confirm_close=True,
            js_api=self.js_api,
        )

        if self.js_api:
            self.js_api.set_window(self.window)

        webview.start(
            debug=False,
            http_server=False,
            private_mode=False,
            storage_path=str(Path.home() / ".ptu"),
            menu=tray_menu,
        )

        # 窗口关闭后保存状态
        self._on_closing()
        print("[桌面客户端] 已退出")


def main():
    print("=" * 50)
    print("  Ptu v1.1.0 - Windows 桌面客户端")
    print("=" * 50)
    print()

    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    main()
