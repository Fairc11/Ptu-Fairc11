from __future__ import annotations

import zipfile
from pathlib import Path

from backend.app.main import _redact_diagnostic_text, _zip_tree


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
