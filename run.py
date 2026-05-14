#!/usr/bin/env python3
"""Ptu - 桌面客户端启动入口

双击运行直接打开桌面窗口。
"""
from __future__ import annotations
import os
import sys
import subprocess
import threading

os.environ.setdefault("PYTHONUTF8", "1")

_frozen = getattr(sys, 'frozen', False)

VERSION = "1.3.0"  # Must match backend/app/version.py


def _kill_port(port: int):
    try:
        output = subprocess.check_output(
            f"netstat -ano | findstr :{port}",
            shell=True, text=True, timeout=5
        )
        for line in output.split("\n"):
            if "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                subprocess.run(f"taskkill /F /PID {pid} 2>nul",
                               shell=True, capture_output=True)
    except Exception:
        pass


def main():
    _start_ts = __import__('time').time()
    # 启动日志文件（无论 console 与否都记录）
    _log_f = open("ptu_boot.log", "a", encoding="utf-8")
    def _log(msg):
        _ts = __import__('time').time() - _start_ts
        _full = f"[t={_ts:.2f}s] {msg}"
        # 控制台输出（窗口模式 sys.stdout 可能为 None）
        if sys.stdout:
            sys.stdout.write(_full + "\n")
            sys.stdout.flush()
        # 文件日志始终可写
        _log_f.write(_full + "\n")
        _log_f.flush()

    _log(f"[Ptu] v{VERSION} 启动中...")
    _kill_port(8000)

    # 打包后自动检测并安装缺失组件（不阻塞启动）
    try:
        import importlib.util
        if importlib.util.find_spec("setup_check"):
            from setup_check import check_playwright
            if not check_playwright():
                from setup_check import run_setup
                t = threading.Thread(target=run_setup, daemon=True)
                t.start()
    except Exception as e:
        _log(f"[Ptu] setup_check 跳过: {e}")

    # 尝试桌面模式
    try:
        from desktop_app import main as desktop_main
        _log("[Ptu] desktop_app 已加载，启动桌面模式...")
        desktop_main()
        return
    except (ImportError, ModuleNotFoundError) as _e:
        _log(f"[Ptu] desktop_app 不可用 ({_e})，走 Web 模式")

    # Web 模式：先导入 app 再启动 uvicorn
    _log("[Ptu] 正在导入 backend.app.main...")
    from backend.app.main import app
    _log("[Ptu] app 导入成功，启动 uvicorn...")
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        import traceback
        try:
            with open("ptu_error.log", "w", encoding="utf-8") as _f:
                _f.write(f"Ptu v{VERSION} 崩溃: {_e}\n{traceback.format_exc()}")
        except Exception:
            pass
        raise
