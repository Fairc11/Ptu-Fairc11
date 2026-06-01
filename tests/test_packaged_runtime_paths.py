from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_packaged_config_uses_local_app_data_for_runtime_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Ptu\Ptu.exe")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    import backend.app.config as config

    try:
        config = importlib.reload(config)
        settings = config.Settings.load_yaml()

        assert settings.data_dir == tmp_path / "LocalAppData" / "Ptu" / "data"
        assert settings.download_dir == tmp_path / "LocalAppData" / "Ptu" / "data" / "downloads"
        assert settings.output_dir == tmp_path / "LocalAppData" / "Ptu" / "data" / "output"
        assert settings.tasks_db == tmp_path / "LocalAppData" / "Ptu" / "data" / "tasks.json"
        assert Path(settings.cookies_path) == tmp_path / "LocalAppData" / "Ptu" / "cookies.yaml"
    finally:
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        importlib.reload(config)


def test_packaged_log_paths_use_local_app_data(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Ptu\Ptu.exe")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    import backend.app.log_config as log_config

    try:
        log_config = importlib.reload(log_config)

        expected_root = tmp_path / "LocalAppData" / "Ptu"
        assert log_config.LOG_DIR == expected_root / "data" / "logs"
        assert log_config.RUNS_DIR == expected_root / "data" / "logs" / "runs"
        assert log_config.EXPORTS_DIR == expected_root / "data" / "logs" / "exports"
        assert log_config.get_boot_log_path() == expected_root / "ptu_boot.log"
    finally:
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        importlib.reload(log_config)
