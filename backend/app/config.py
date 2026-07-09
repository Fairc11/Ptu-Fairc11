"""
Configuration module.

Handles path resolution for both development and packaged (PyInstaller) environments.
"""
from __future__ import annotations
import os
import sys
import shutil
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
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Ptu"
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Ptu"
        if sys.platform.startswith("win"):
            return Path.home() / "AppData" / "Local" / "Ptu"
        return Path.home() / ".local" / "share" / "Ptu"
    return _get_base_dir()


def _ffmpeg_names() -> list[str]:
    if sys.platform.startswith("win"):
        return ["ffmpeg.exe", "ffmpeg"]
    return ["ffmpeg"]


def _is_usable_ffmpeg_path(path: Path) -> bool:
    if path.name.lower().endswith(".exe") and not sys.platform.startswith("win"):
        return False
    if not path.exists():
        return False
    if sys.platform.startswith("win"):
        return True
    return os.access(path, os.X_OK)


def _find_ffmpeg() -> str:
    """Search for a platform-usable FFmpeg executable."""
    ffmpeg = "ffmpeg"
    names = _ffmpeg_names()

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
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            search_paths.insert(0, Path(meipass))
    elif not sys.platform.startswith("win"):
        found = shutil.which("ffmpeg")
        if found:
            return found

    for base in search_paths:
        for pattern in names:
            candidates = list(base.rglob(pattern))
            usable = [candidate for candidate in candidates if _is_usable_ffmpeg_path(candidate)]
            if usable:
                return str(usable[0])

    found = shutil.which("ffmpeg")
    if found:
        return found

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
        if s.ffmpeg_path == "ffmpeg" or not _is_usable_ffmpeg_path(Path(s.ffmpeg_path)):
            s.ffmpeg_path = _find_ffmpeg()

        return s


def _resolve_path(p: Path, base: Path) -> Path:
    """Resolve path relative to base if not absolute."""
    if not p.is_absolute():
        return (base / p).resolve()
    return p


settings = Settings.load_yaml()
