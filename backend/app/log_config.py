"""
Centralized logging configuration for Ptu.

Logs to:
  - data/logs/ptu.log (rotating, max 5MB, keep 3 backups)
  - stdout (dev mode only, not in frozen windowless mode)
"""
from __future__ import annotations
import sys
import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "data" / "logs"


def setup_logging(debug: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "ptu.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # File handler (rotating)
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5_242_880, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root.addHandler(fh)

    # Console handler (only if stdout is available, e.g. dev mode)
    if sys.stdout and not getattr(sys, "frozen", False):
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG if debug else logging.INFO)
        ch.setFormatter(logging.Formatter(
            "[%(levelname)s] %(message)s"
        ))
        root.addHandler(ch)

    # Suppress noisy third-party loggers
    for lg in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection",
               "f2", "f2.apps.douyin", "f2.crawlers",
               "playwright", "websockets", "uvicorn"):
        logging.getLogger(lg).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
