# -*- mode: python ; coding: utf-8 -*-
"""
Ptu - PyInstaller 打包配置 (--onedir 模式)
用法: pyinstaller build.spec

输出 dist/Ptu/Ptu.exe + dist/Ptu/_internal/ 目录
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

# 收集 f2 库的配置文件
import importlib.util as _iutil
_f2_spec = _iutil.find_spec('f2')
if _f2_spec and _f2_spec.submodule_search_locations:
    _f2_conf = Path(_f2_spec.submodule_search_locations[0]) / 'conf'
    if _f2_conf.exists():
        for _f in _f2_conf.rglob('*'):
            if _f.is_file() and _f.suffix in ('.yaml', '.yml'):
                datas.append((str(_f), 'f2/conf'))

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
        'websockets',
        'playwright',
        'playwright.async_api',
        'browser_cookie3',
        'pywebview',
        'webview',
        'webview.platforms.winforms',
        'plyer',
        'win32api',
        'win32event',
        # f2 库
        'f2',
        'f2.apps.douyin',
        'f2.apps.douyin.handler',
        'f2.apps.douyin.crawler',
        'f2.apps.douyin.dl',
        'f2.apps.douyin.model',
        'f2.apps.douyin.filter',
        'f2.apps.douyin.utils',
        'f2.apps.douyin.db',
        'f2.apps.douyin.algorithm',
        'f2.apps.bark.handler',
        'f2.apps.bark.utils',
        'f2.log.logger',
        'f2.i18n.translator',
        'f2.utils.conf_manager',
        'f2.utils.decorators',
        'f2.utils.utils',
        'f2.utils.abogus',
        'f2.utils.xbogus',
        'f2.exceptions',
        'f2.exceptions.api_exceptions',
        'f2.cli.cli_console',
    ],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
        'PyQt5', 'PySide2', 'PySide6',
        'setuptools', 'pip', 'pytest', 'unittest',
        'cryptography',
    ],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --onedir 模式：生成 Ptu.exe + _internal/ 目录
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

# 收集所有依赖到 _internal/ 目录
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Ptu',
)
