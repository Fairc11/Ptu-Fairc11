from __future__ import annotations

import logging
import os
import sys
import time

from backend.app import log_config


def test_setup_logging_creates_run_log_and_captures_print(tmp_path, monkeypatch):
    monkeypatch.setattr(log_config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(log_config, "RUNS_DIR", tmp_path / "logs" / "runs")
    monkeypatch.setattr(log_config, "EXPORTS_DIR", tmp_path / "logs" / "exports")

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        log_config.setup_logging(debug=False)
        run_log = log_config.get_current_run_log()
        assert run_log is not None
        assert run_log.exists()

        print("auto log capture works")
        sys.stdout.flush()

        text = run_log.read_text(encoding="utf-8")
        assert "日志系统已启动" in text
        assert "auto log capture works" in text
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        root = logging.getLogger()
        for handler in list(root.handlers):
            if getattr(handler, "_ptu_handler", False):
                root.removeHandler(handler)
                handler.close()


def test_cleanup_runtime_logs_removes_runs_and_exports_older_than_keep_days(tmp_path, monkeypatch):
    runs_dir = tmp_path / "logs" / "runs"
    exports_dir = tmp_path / "logs" / "exports"
    runs_dir.mkdir(parents=True)
    exports_dir.mkdir(parents=True)
    monkeypatch.setattr(log_config, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(log_config, "EXPORTS_DIR", exports_dir)

    old_run = runs_dir / "ptu_2026-01-01_010101.log"
    old_export = exports_dir / "ptu_run_20260101_010101.log"
    fresh_run = runs_dir / "ptu_2099-01-01_010101.log"
    for path in (old_run, old_export, fresh_run):
        path.write_text("log", encoding="utf-8")

    old_ts = time.time() - 9 * 24 * 60 * 60
    os.utime(old_run, (old_ts, old_ts))
    os.utime(old_export, (old_ts, old_ts))

    log_config.cleanup_runtime_logs(keep_days=7)

    assert not old_run.exists()
    assert not old_export.exists()
    assert fresh_run.exists()
