#!/usr/bin/env python3
"""Ptu v1.1.0 - 桌面客户端启动入口

双击运行直接打开桌面窗口。
"""
from __future__ import annotations
import os
import sys
import subprocess
import threading

os.environ.setdefault("PYTHONUTF8", "1")

_frozen = getattr(sys, 'frozen', False)


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
    except Exception:
        pass

    from desktop_app import main as desktop_main
    desktop_main()


if __name__ == "__main__":
    main()
