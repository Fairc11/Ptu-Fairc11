# -*- mode: python ; coding: utf-8 -*-
"""
Ptu - macOS PyInstaller .app prototype.

Usage:
    PTU_MAC_FFMPEG_DIR=/path/to/ffmpeg/bin python -m PyInstaller build_macos.spec
"""
import os
import shutil
import sys
from pathlib import Path

block_cipher = None
root = Path(os.getcwd())

if sys.platform != "darwin":
    raise SystemExit("build_macos.spec must be used on macOS")

datas = []

backend_dir = root / "backend"
for f in backend_dir.rglob("*"):
    if (
        f.is_file()
        and "__pycache__" not in f.parts
        and f.suffix != ".pyc"
        and f.name not in (".env", "cookies.yaml")
    ):
        rel = f.relative_to(root)
        datas.append((str(f), str(rel.parent)))

for name in ["config.yaml"]:
    p = root / name
    if p.exists():
        datas.append((str(p), "."))

import certifi
_cacert = Path(certifi.where())
if _cacert.exists():
    datas.append((str(_cacert), "certifi"))

import importlib.util as _iutil
_f2_spec = _iutil.find_spec("f2")
if _f2_spec and _f2_spec.submodule_search_locations:
    _f2_conf = Path(_f2_spec.submodule_search_locations[0]) / "conf"
    if _f2_conf.exists():
        for _f in _f2_conf.rglob("*"):
            if _f.is_file() and _f.suffix in (".yaml", ".yml"):
                datas.append((str(_f), "f2/conf"))

_playwright_roots = []
if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    _playwright_roots.append(Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]))
_playwright_roots.extend([
    Path.home() / "Library" / "Caches" / "ms-playwright",
    Path.home() / ".cache" / "ms-playwright",
])

_bundled_shell = None
for _root in _playwright_roots:
    if not _root.exists():
        continue
    for _candidate in sorted(_root.glob("chromium_headless_shell-*"), reverse=True):
        if any(_candidate.rglob("chrome-headless-shell")):
            _bundled_shell = _candidate
            break
    if _bundled_shell:
        break

if _bundled_shell and _bundled_shell.exists():
    datas.append((str(_bundled_shell), f"ms-playwright/{_bundled_shell.name}"))
else:
    raise SystemExit("Missing macOS Playwright chromium_headless_shell-*")

_mac_ffmpeg_dir = Path(os.environ.get("PTU_MAC_FFMPEG_DIR", ""))
if not _mac_ffmpeg_dir.exists():
    _ffmpeg = shutil.which("ffmpeg")
    _ffprobe = shutil.which("ffprobe")
    if _ffmpeg and _ffprobe and Path(_ffmpeg).parent == Path(_ffprobe).parent:
        _mac_ffmpeg_dir = Path(_ffmpeg).parent

_ffmpeg = _mac_ffmpeg_dir / "ffmpeg"
_ffprobe = _mac_ffmpeg_dir / "ffprobe"
if not (_ffmpeg.exists() and os.access(_ffmpeg, os.X_OK)):
    raise SystemExit("Missing executable macOS ffmpeg")
if not (_ffprobe.exists() and os.access(_ffprobe, os.X_OK)):
    raise SystemExit("Missing executable macOS ffprobe")
datas.append((str(_ffmpeg), "."))
datas.append((str(_ffprobe), "."))

_third_party_notices = root / "THIRD_PARTY_NOTICES.md"
if _third_party_notices.exists():
    datas.append((str(_third_party_notices), "."))

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "setup_check",
        "uvicorn",
        "starlette",
        "starlette.routing",
        "starlette.middleware",
        "starlette.staticfiles",
        "starlette.templating",
        "jinja2",
        "jinja2.ext",
        "httpx",
        "certifi",
        "yaml",
        "PIL",
        "pillow_heif",
        "anyio",
        "sniffio",
        "multipart",
        "pydantic",
        "pydantic_settings",
        "websockets",
        "playwright",
        "playwright.async_api",
        "webview",
        "webview.platforms.cocoa",
        "plyer",
        "f2",
        "f2.apps.douyin",
        "f2.apps.douyin.handler",
        "f2.apps.douyin.crawler",
        "f2.apps.douyin.dl",
        "f2.apps.douyin.model",
        "f2.apps.douyin.filter",
        "f2.apps.douyin.utils",
        "f2.apps.douyin.db",
        "f2.apps.douyin.algorithm",
        "f2.apps.bark.handler",
        "f2.apps.bark.utils",
        "f2.log.logger",
        "f2.i18n.translator",
        "f2.utils.conf_manager",
        "f2.utils.decorators",
        "f2.utils.utils",
        "f2.utils.abogus",
        "f2.utils.xbogus",
        "f2.exceptions",
        "f2.exceptions.api_exceptions",
        "f2.cli.cli_console",
    ],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "PyQt5",
        "PySide2",
        "PySide6",
        "setuptools",
        "pip",
        "pytest",
        "unittest",
    ],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ptu",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Ptu-macos",
)

app = BUNDLE(
    coll,
    name='Ptu.app',
    icon=str(root / "icon.ico") if (root / "icon.ico").exists() else None,
    bundle_identifier='com.fairc11.ptu',
    info_plist={
        "CFBundleName": "Ptu",
        "CFBundleDisplayName": "Ptu",
        "CFBundleShortVersionString": "1.5.0",
        "CFBundleVersion": "1.5.0",
        "NSHighResolutionCapable": True,
    },
)
