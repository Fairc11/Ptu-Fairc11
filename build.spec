# -*- mode: python ; coding: utf-8 -*-
"""
Ptu - PyInstaller 打包配置
用法: pyinstaller build.spec
"""
import os
import sys
from pathlib import Path

block_cipher = None
root = Path(os.getcwd())

# 收集所有 backend 数据文件
backend_dir = root / 'backend'
datas = []
for f in backend_dir.rglob('*'):
    if f.is_file() and '__pycache__' not in f.parts and '.pyc' not in f.suffix:
        rel = f.relative_to(root)
        datas.append((str(f), str(rel.parent)))

# 收集根目录配置文件
for f in ['cookies.yaml', 'config.yaml']:
    p = root / f
    if p.exists():
        datas.append((str(p), '.'))

a = Analysis(
    [str(root / 'run.py')],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'setup_check',
        'uvicorn',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.staticfiles',
        'starlette.templating',
        'jinja2',
        'jinja2.ext',
        'httpx',
        'yaml',
        'PIL',
        'pillow_heif',
        'anyio',
        'sniffio',
        'multipart',
        'pydantic',
        'pydantic_settings',
        'email',
        'email.mime',
        'email.mime.multipart',
        'email.mime.text',
        'websockets',
        'playwright',
        'playwright.async_api',
        'browser_cookie3',
        'pydantic_core',
        'pyi_splash',
        'pywebview',
        'webview',
        'webview.platforms.winforms',
        'plyer',
        'win32api',
        'win32event',
    ],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
        'PyQt5', 'PySide2', 'PySide6',
        'setuptools', 'pip', 'pytest', 'unittest',
        'cryptography',
    ],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Ptu',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(root / 'icon.ico') if (root / 'icon.ico').exists() else None,
    uac_admin=False,
)
