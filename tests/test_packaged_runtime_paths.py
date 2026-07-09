from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_packaged_config_uses_local_app_data_for_runtime_files(tmp_path, monkeypatch):
    import backend.app.config as config

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Ptu\Ptu.exe")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    try:
        config = importlib.reload(config)
        monkeypatch.setattr(config.sys, "platform", "win32")
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
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Ptu\Ptu.exe")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    import backend.app.log_config as log_config

    try:
        log_config = importlib.reload(log_config)

        expected_root = tmp_path / "LocalAppData" / "Ptu"
        assert log_config.LOG_DIR == expected_root / "日志"
        assert log_config.RUNS_DIR == expected_root / "日志" / "runs"
        assert log_config.EXPORTS_DIR == expected_root / "日志" / "exports"
        assert log_config.get_boot_log_path() == expected_root / "日志" / "ptu_boot.log"
    finally:
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        importlib.reload(log_config)


def test_packaged_config_uses_application_support_on_macos(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", "/Applications/Ptu.app/Contents/MacOS/Ptu")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("PTU_RUNTIME_DIR", raising=False)

    import backend.app.config as config

    try:
        config = importlib.reload(config)
        settings = config.Settings.load_yaml()

        expected_root = Path.home() / "Library" / "Application Support" / "Ptu"
        assert settings.data_dir == expected_root / "data"
        assert settings.download_dir == expected_root / "data" / "downloads"
        assert settings.output_dir == expected_root / "data" / "output"
        assert settings.tasks_db == expected_root / "data" / "tasks.json"
        assert Path(settings.cookies_path) == expected_root / "cookies.yaml"
    finally:
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        importlib.reload(config)


def test_packaged_log_paths_use_application_support_on_macos(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", "/Applications/Ptu.app/Contents/MacOS/Ptu")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("PTU_RUNTIME_DIR", raising=False)

    import backend.app.log_config as log_config

    try:
        log_config = importlib.reload(log_config)

        expected_root = Path.home() / "Library" / "Application Support" / "Ptu"
        assert log_config.LOG_DIR == expected_root / "日志"
        assert log_config.RUNS_DIR == expected_root / "日志" / "runs"
        assert log_config.EXPORTS_DIR == expected_root / "日志" / "exports"
        assert log_config.get_boot_log_path() == expected_root / "日志" / "ptu_boot.log"
    finally:
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        importlib.reload(log_config)


def test_setup_check_runtime_dir_uses_application_support_on_macos(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("PTU_RUNTIME_DIR", raising=False)

    import setup_check

    try:
        setup_check = importlib.reload(setup_check)

        assert setup_check._get_runtime_dir() == Path.home() / "Library" / "Application Support" / "Ptu"
    finally:
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        importlib.reload(setup_check)


def test_run_runtime_dir_uses_application_support_on_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("PTU_RUNTIME_DIR", raising=False)

    import run

    assert run._default_runtime_dir() == Path.home() / "Library" / "Application Support" / "Ptu"
