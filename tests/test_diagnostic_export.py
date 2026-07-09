from __future__ import annotations

import zipfile
import sys
from pathlib import Path

from backend.app.main import _redact_diagnostic_text, _zip_tree
from backend.app import log_config, main


def test_diagnostic_log_export_redacts_cookie_values():
    text = "\n".join([
        "Cookie: sessionid=abc; sid_tt=def",
        "sessionid=abc123",
        "msToken: token-value",
    ])

    redacted = _redact_diagnostic_text(text)

    assert "abc123" not in redacted
    assert "token-value" not in redacted
    assert "sessionid=[REDACTED]" in redacted
    assert "Cookie: [REDACTED]" in redacted


def test_diagnostic_zip_tree_excludes_raw_cookies_and_keeps_folders(tmp_path):
    downloads = tmp_path / "data" / "downloads" / "task"
    downloads.mkdir(parents=True)
    (downloads / "image.jpg").write_bytes(b"image")
    (tmp_path / "cookies.yaml").write_text("sessionid: secret", encoding="utf-8")
    log_dir = tmp_path / "日志"
    log_dir.mkdir()
    (log_dir / "ptu.log").write_text("Cookie: sessionid=secret", encoding="utf-8")
    zip_path = tmp_path / "diagnostic.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        _zip_tree(zf, downloads.parent, "data/downloads")
        _zip_tree(zf, tmp_path / "cookies.yaml", "data")
        _zip_tree(zf, log_dir, "日志", redact_text=True)

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        log_text = zf.read("日志/ptu.log").decode("utf-8")

    assert "data/downloads/task/image.jpg" in names
    assert "data/cookies.yaml" not in names
    assert "secret" not in log_text


def test_diagnostic_package_uses_fast_zip_storage():
    source = Path("backend/app/main.py").read_text(encoding="utf-8")

    assert "ZIP_STORED" in source
    assert "avoids long" in source


def test_diagnostic_package_accepts_string_cookies_path(tmp_path, monkeypatch):
    log_dir = tmp_path / "日志"
    runs_dir = log_dir / "runs"
    exports_dir = log_dir / "exports"
    downloads_dir = tmp_path / "data" / "downloads"
    output_dir = tmp_path / "data" / "output"
    tasks_db = tmp_path / "data" / "tasks.json"
    run_log = runs_dir / "ptu_test.log"

    runs_dir.mkdir(parents=True)
    downloads_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    tasks_db.parent.mkdir(parents=True, exist_ok=True)
    tasks_db.write_text("[]", encoding="utf-8")
    run_log.write_text("Cookie: sessionid=secret", encoding="utf-8")

    monkeypatch.setattr(log_config, "LOG_DIR", log_dir)
    monkeypatch.setattr(log_config, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(log_config, "EXPORTS_DIR", exports_dir)
    monkeypatch.setattr(log_config, "get_current_run_log", lambda: run_log)
    monkeypatch.setattr(main.settings, "download_dir", downloads_dir)
    monkeypatch.setattr(main.settings, "output_dir", output_dir)
    monkeypatch.setattr(main.settings, "tasks_db", tasks_db)
    monkeypatch.setattr(main.settings, "ffmpeg_path", str(tmp_path / "ffmpeg"))
    monkeypatch.setattr(main.settings, "cookies_path", str(tmp_path / "cookies.yaml"))

    zip_path = main._create_diagnostic_package()

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        diagnostic = zf.read("diagnostic.txt").decode("utf-8")
        run_log_text = zf.read("logs/ptu_test.log").decode("utf-8")

    assert "diagnostic.txt" in names
    assert "Cookies file exists: False" in diagnostic
    if not sys.platform.startswith("win"):
        assert "ffprobe.exe" not in diagnostic
    assert "secret" not in run_log_text
