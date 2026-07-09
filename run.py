#!/usr/bin/env python3
"""Ptu - 桌面客户端启动入口

双击运行直接打开桌面窗口。
"""
from __future__ import annotations
import os
import sys
import subprocess
import threading
import signal
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")

# 封包后设置 SSL 证书路径（certifi 在 frozen 环境找不到 cacert.pem）
if getattr(sys, 'frozen', False):
    _cacert = Path(sys._MEIPASS) / "certifi" / "cacert.pem"
    if _cacert.exists():
        os.environ["SSL_CERT_FILE"] = str(_cacert)
        os.environ["REQUESTS_CA_BUNDLE"] = str(_cacert)

_frozen = getattr(sys, 'frozen', False)


def _default_runtime_dir() -> Path:
    configured = os.environ.get("PTU_RUNTIME_DIR")
    if configured:
        return Path(configured)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Ptu"
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Ptu"
    if sys.platform.startswith("win"):
        return Path.home() / "AppData" / "Local" / "Ptu"
    return Path.home() / ".local" / "share" / "Ptu"


if _frozen:
    os.environ.setdefault("PTU_RUNTIME_DIR", str(_default_runtime_dir()))

from backend.app.version import VERSION


def _should_run_setup(check_playwright, check_ffmpeg) -> bool:
    return (not check_playwright()) or (not check_ffmpeg())


def _is_web_mode(argv: list[str]) -> bool:
    return any(arg in ("--web", "-w") for arg in argv[1:])


def _get_boot_log_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(os.environ["PTU_RUNTIME_DIR"]) / "日志"
    return Path(__file__).parent / "日志"


def _kill_port(port: int):
    try:
        if not sys.platform.startswith("win"):
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for pid in result.stdout.splitlines():
                if pid.strip():
                    os.kill(int(pid.strip()), signal.SIGTERM)
            return

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
    # 封包安装到 Program Files 后不可写，运行时日志必须放到用户目录。
    _log_dir = _get_boot_log_dir()
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_f = open(str(_log_dir / "ptu_boot.log"), "a", encoding="utf-8")
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
            from setup_check import check_ffmpeg, check_playwright
            if _should_run_setup(check_playwright, check_ffmpeg):
                from setup_check import run_setup
                t = threading.Thread(target=run_setup, daemon=True)
                t.start()
    except Exception as e:
        _log(f"[Ptu] setup_check 跳过: {e}")

    if _is_web_mode(sys.argv):
        _log("[Ptu] Web 模式启动")
        _log("[Ptu] 正在导入 backend.app.main...")
        from backend.app.main import app
        _log("[Ptu] app 导入成功，启动 uvicorn...")
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
        return

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
            _err_dir = _get_boot_log_dir()
            _err_dir.mkdir(parents=True, exist_ok=True)
            _err_log = _err_dir / "ptu_error.log"
            with open(str(_err_log), "w", encoding="utf-8") as _f:
                _f.write(f"Ptu v{VERSION} 崩溃: {_e}\n{traceback.format_exc()}")
        except Exception:
            pass
        raise
