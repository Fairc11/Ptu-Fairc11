"""
Centralized logging configuration for Ptu.

Logs to:
  - 日志/ptu.log (rotating, max 5MB, keep 3 backups — for log panel)
  - 日志/ptu_boot.log (startup log)
  - 日志/runs/ptu_YYYY-MM-DD_HHMMSS.log (per-run files, 7-day auto-clean)
  - 日志/runs/ptu_YYYY-MM-DD.log (daily rollup, 7-day auto-clean)
  - 日志/exports/ptu_run_YYYYMMDD_HHMMSS.log (manual snapshots, 7-day auto-clean)
  - stdout (dev mode only)
"""
from __future__ import annotations
import os
import sys
import logging
import logging.handlers
from datetime import datetime, timedelta
from pathlib import Path

from .version import VERSION

LOG_FOLDER_NAME = "日志"


def get_runtime_dir() -> Path:
    """Return the user-writable runtime directory for packaged installs."""
    if getattr(sys, 'frozen', False):
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
    return Path(__file__).parent.parent.parent


def get_log_dir() -> Path:
    """Return the obvious user-facing log folder."""
    return get_runtime_dir() / LOG_FOLDER_NAME


LOG_DIR = get_log_dir()
RUNS_DIR = LOG_DIR / "runs"
EXPORTS_DIR = LOG_DIR / "exports"
CURRENT_RUN_LOG: Path | None = None
_ORIGINAL_STDOUT = sys.stdout
_ORIGINAL_STDERR = sys.stderr


class _StreamToLogger:
    """Mirror print/stdout output into logging without losing console output."""

    def __init__(self, logger_name: str, level: int, original_stream):
        self.logger = logging.getLogger(logger_name)
        self.level = level
        self.original_stream = original_stream
        self._buffer = ""

    def write(self, message: str):
        if self.original_stream:
            try:
                self.original_stream.write(message)
            except Exception:
                pass
        if not message:
            return
        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                self.logger.log(self.level, line)

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass
        if self._buffer.strip():
            self.logger.log(self.level, self._buffer.strip())
        self._buffer = ""


def _cleanup_old_logs(keep_days: int = 7) -> None:
    """Delete auto-saved run/export logs older than keep_days."""
    cutoff = datetime.now() - timedelta(days=keep_days)

    def cleanup_dir(path: Path, patterns: tuple[str, ...]) -> None:
        if not path.exists():
            return
        for pattern in patterns:
            for f in path.glob(pattern):
                try:
                    if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                        f.unlink()
                        continue
                    # Filename date fallback for copied/restored files with fresh mtime.
                    stem = f.stem.replace("ptu_run_", "").replace("ptu_log_", "").replace("ptu_", "")
                    file_date = datetime.strptime(stem[:10], "%Y-%m-%d")
                    if file_date < cutoff:
                        f.unlink()
                except (ValueError, OSError):
                    pass

    cleanup_dir(RUNS_DIR, ("ptu_*.log",))
    cleanup_dir(EXPORTS_DIR, ("ptu_run_*.log", "ptu_log_*.log"))


def cleanup_runtime_logs(keep_days: int = 7) -> None:
    """Public helper for scheduled/manual log retention cleanup."""
    _cleanup_old_logs(keep_days=keep_days)


def setup_logging(debug: bool = False) -> None:
    global CURRENT_RUN_LOG
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 清理 7 天前的日志
    _cleanup_old_logs()

    log_file = LOG_DIR / "ptu.log"
    now = datetime.now()
    run_file = RUNS_DIR / f"ptu_{now.strftime('%Y-%m-%d_%H%M%S')}.log"
    daily_file = RUNS_DIR / f"ptu_{now.strftime('%Y-%m-%d')}.log"
    CURRENT_RUN_LOG = run_file

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Avoid duplicate handlers when dev reload/tests call setup repeatedly.
    for handler in list(root.handlers):
        if getattr(handler, "_ptu_handler", False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    # File handler (rotating — for log panel)
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5_242_880, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    fh._ptu_handler = True
    root.addHandler(fh)

    # Per-run log file: every app launch gets its own automatically saved file.
    rfh = logging.FileHandler(run_file, encoding="utf-8")
    rfh.setLevel(logging.DEBUG)
    rfh.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    rfh._ptu_handler = True
    root.addHandler(rfh)

    # Daily rollup log file (for quick date-based lookup).
    dfh = logging.FileHandler(daily_file, encoding="utf-8")
    dfh.setLevel(logging.DEBUG)
    dfh.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    dfh._ptu_handler = True
    root.addHandler(dfh)

    # Console handler (only if stdout is available, e.g. dev mode)
    if _ORIGINAL_STDOUT and not getattr(sys, "frozen", False):
        ch = logging.StreamHandler(_ORIGINAL_STDOUT)
        ch.setLevel(logging.DEBUG if debug else logging.INFO)
        ch.setFormatter(logging.Formatter(
            "[%(levelname)s] %(message)s"
        ))
        ch._ptu_handler = True
        root.addHandler(ch)

    # Suppress noisy third-party loggers
    for lg in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection",
               "f2", "f2.apps.douyin", "f2.crawlers",
               "playwright", "websockets", "uvicorn"):
        logging.getLogger(lg).setLevel(logging.WARNING)

    # Capture print() output used by older code paths into the same log files.
    if not isinstance(sys.stdout, _StreamToLogger):
        sys.stdout = _StreamToLogger("stdout", logging.INFO, _ORIGINAL_STDOUT)
    if not isinstance(sys.stderr, _StreamToLogger):
        sys.stderr = _StreamToLogger("stderr", logging.ERROR, _ORIGINAL_STDERR)

    logging.getLogger("app").info(
        "Ptu v%s 日志系统已启动，当前运行日志: %s", VERSION, run_file
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def get_current_run_log() -> Path | None:
    return CURRENT_RUN_LOG


def get_boot_log_path() -> Path:
    return get_log_dir() / "ptu_boot.log"
