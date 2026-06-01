"""
Configuration module.

Handles path resolution for both development and packaged (PyInstaller) environments.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
import yaml
from pydantic_settings import BaseSettings


def _get_base_dir() -> Path:
    """Get the base directory (app root) in dev and packaged mode."""
    if getattr(sys, 'frozen', False):
        # PyInstaller packaged exe: base is alongside the exe
        return Path(sys.executable).parent
    else:
        # Development: project root (where run.py / desktop_app.py lives)
        return Path(__file__).parent.parent.parent


def _get_runtime_dir() -> Path:
    """Get user-writable runtime data root in packaged mode."""
    if getattr(sys, 'frozen', False):
        configured = os.environ.get("PTU_RUNTIME_DIR")
        if configured:
            return Path(configured)
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Ptu"
        return Path.home() / "AppData" / "Local" / "Ptu"
    return _get_base_dir()


def _find_ffmpeg() -> str:
    """Search for ffmpeg.exe in common locations."""
    # Check PATH first
    ffmpeg = "ffmpeg"

    # Common install paths
    search_paths = [
        _get_runtime_dir(),
        _get_runtime_dir() / "ffmpeg",
        Path(os.environ.get("LOCALAPPDATA", "")) / "ffmpeg",
        Path(os.environ.get("PROGRAMFILES", "")) / "ffmpeg" / "bin",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "ffmpeg" / "bin",
        Path("C:\\ffmpeg\\bin"),
        Path("C:\\tools\\ffmpeg\\bin"),
    ]
    # In frozen mode, also search alongside the exe
    if getattr(sys, 'frozen', False):
        search_paths.insert(0, Path(sys.executable).parent)

    for base in search_paths:
        for pattern in ["ffmpeg.exe", "ffmpeg"]:
            candidates = list(base.rglob(pattern))
            if candidates:
                return str(candidates[0])

    return ffmpeg


class Settings(BaseSettings):
    # Paths
    data_dir: Path = Path("data")
    download_dir: Path = data_dir / "downloads"
    output_dir: Path = data_dir / "output"
    tasks_db: Path = data_dir / "tasks.json"

    # FFmpeg
    ffmpeg_path: str = "ffmpeg"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # Douyin cookies path
    cookies_path: str = "cookies.yaml"

    # Concurrency
    max_concurrent_downloads: int = 3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @classmethod
    def load_yaml(cls) -> "Settings":
        s = cls()
        base = _get_base_dir()
        runtime_base = _get_runtime_dir()

        # Search config.yaml in multiple locations
        search_paths = [
            base / "backend" / "config.yaml",
            base / "config.yaml",
            Path(__file__).parent.parent.parent / "config.yaml",
        ]
        config_file = None
        for sp in search_paths:
            if sp and sp.exists():
                config_file = sp
                break

        if config_file:
            try:
                data = yaml.safe_load(config_file.read_text("utf-8"))
                if data:
                    for k, v in data.items():
                        if hasattr(s, k) and v is not None:
                            setattr(s, k, v)
            except Exception:
                pass

        # Resolve relative paths
        s.data_dir = _resolve_path(s.data_dir, runtime_base)
        s.download_dir = _resolve_path(s.download_dir, runtime_base)
        s.output_dir = _resolve_path(s.output_dir, runtime_base)
        s.tasks_db = _resolve_path(s.tasks_db, runtime_base)
        s.cookies_path = str(_resolve_path(Path(s.cookies_path), runtime_base))

        # Auto-detect FFmpeg if not found
        if s.ffmpeg_path == "ffmpeg" or not Path(s.ffmpeg_path).exists():
            s.ffmpeg_path = _find_ffmpeg()

        return s


def _resolve_path(p: Path, base: Path) -> Path:
    """Resolve path relative to base if not absolute."""
    if not p.is_absolute():
        return (base / p).resolve()
    return p


settings = Settings.load_yaml()
