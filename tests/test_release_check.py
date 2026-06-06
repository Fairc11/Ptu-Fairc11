from __future__ import annotations

from pathlib import Path

from scripts.release_check import collect_release_findings, read_project_version


def _write_valid_release_fixture(root: Path) -> None:
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "static" / "js").mkdir(parents=True)
    (root / "backend" / "app" / "templates").mkdir(parents=True)
    (root / "backend" / "app" / "services").mkdir(parents=True)
    (root / "backend" / "app" / "api").mkdir(parents=True)
    (root / "backend" / "app" / "version.py").write_text('VERSION = "1.5.0"\n', encoding="utf-8")
    (root / "backend" / "app" / "js_api.py").write_text(
        "class JsApi:\n"
        "    def get_clipboard(self):\n"
        "        return ''\n"
        "    def open_douyin_panel(self, url=''):\n"
        "        return {'status': 'ok'}\n"
        "    def mount_douyin_panel(self, rect=None, visible=False):\n"
        "        return {'status': 'ok'}\n"
        "    def resize_douyin_panel(self, rect):\n"
        "        return {'status': 'ok'}\n"
        "    def get_douyin_panel_url(self):\n"
        "        return {'status': 'ok', 'url': ''}\n",
        encoding="utf-8",
    )
    (root / "backend" / "app" / "desktop_douyin_panel.py").write_text(
        "class NativeDouyinPanel:\n"
        "    def _create(self):\n"
        "        webview = WebView2()\n"
        "        self._form.Controls.Add(webview)\n"
        "        core.NewWindowRequested += self._on_new_window\n"
        "    def _on_new_window(self, sender, args):\n"
        "        args.Handled = True\n",
        encoding="utf-8",
    )
    (root / "backend" / "app" / "static" / "js" / "app.js").write_text(
        "api.post('/api/profile/scrape', {url, max_posts: 30, max_cursor: state.profileNextCursor});\n"
        "desktop.openDouyinPanel(); ui.mountBrowserDock();\n",
        encoding="utf-8",
    )
    (root / "backend" / "app" / "templates" / "index.html").write_text(
        '<aside id="browser-dock"><div id="browser-native-host"></div><div id="browser-login-panel">扫码</div>不自动扫描页面，不自动翻页 手动复制链接</aside><div id="disclaimer-modal">不绕过验证码 同意并进入</div>\n',
        encoding="utf-8",
    )
    (root / "backend" / "app" / "main.py").write_text(
        "@app.get('/api/logs/diagnostic')\n"
        "def export_diagnostic_package():\n"
        "    return '[REDACTED]'\n",
        encoding="utf-8",
    )
    (root / "backend" / "app" / "services" / "media_processor.py").write_text(
        'kwargs = {"encoding": "utf-8", "errors": "replace"}\n'
        "flags = subprocess.CREATE_NO_WINDOW\n"
        "filter = 'xfade=transition=wipeleft'\n",
        encoding="utf-8",
    )
    (root / "backend" / "app" / "services" / "qr_login.py").write_text(
        'print("使用内置 Chromium")\n'
        'await self._get_qrcode_pw(executable_path=exe_path)\n'
        '"--headless=new"\n'
        '"--window-position=-32000,-32000"\n',
        encoding="utf-8",
    )
    (root / "backend" / "app" / "api" / "router_profile.py").write_text(
        "MAX_PROFILE_POSTS = 30\n",
        encoding="utf-8",
    )
    (root / "installer.iss").write_text(
        '#define MyAppVersion "1.5.0"\n'
        'OutputBaseFilename=Ptu_Setup_v{#MyAppVersion}\n'
        'Source: "dist\\Ptu\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs\n',
        encoding="utf-8",
    )
    (root / "build.spec").write_text(
        "hiddenimports=['f2.apps.douyin.handler','playwright.async_api','webview.platforms.winforms']\n"
        "datas=[('conf.yaml', 'f2/conf'), ('cacert.pem', 'certifi')]\n"
        "_vendor_ffmpeg = root / 'vendor' / 'ffmpeg' / 'ffmpeg.exe'\n"
        "_copy_to_dist_root(_vendor_ffmpeg)\n"
        "_vendor_ffprobe = root / 'vendor' / 'ffmpeg' / 'ffprobe.exe'\n"
        "_copy_to_dist_root(_vendor_ffprobe)\n"
        "_third_party_notices = root / 'THIRD_PARTY_NOTICES.md'\n"
        "_copy_to_dist_root(_third_party_notices)\n"
        "for _candidate in _ms_playwright.glob('chromium_headless_shell-*'):\n"
        "    'chrome-headless-shell.exe'\n"
        "excludes=[]\n",
        encoding="utf-8",
    )
    (root / "run.py").write_text("from backend.app.main import app\nuvicorn.run(app)\n", encoding="utf-8")
    (root / "desktop_app.py").write_text("webview.create_window(frameless=False, confirm_close=False)\n", encoding="utf-8")
    (root / "setup_check.py").write_text("def install_playwright():\n    pass\n", encoding="utf-8")
    (root / "build_exe.bat").write_text("ISCC installer.iss\n", encoding="utf-8")


def test_read_project_version_from_version_file(tmp_path: Path):
    version_file = tmp_path / "version.py"
    version_file.write_text('VERSION = "1.4.1"\nAPP_NAME = "Ptu"\n', encoding="utf-8")

    assert read_project_version(version_file) == "1.4.1"


def test_collect_release_findings_flags_version_mismatch(tmp_path: Path):
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "version.py").write_text('VERSION = "1.4.1"\n', encoding="utf-8")
    (tmp_path / "installer.iss").write_text('#define MyAppVersion "1.4.0"\n', encoding="utf-8")
    (tmp_path / "build.spec").write_text(
        "hiddenimports=['f2.apps.douyin.handler']\n"
        "datas.append(('conf.yaml', 'f2/conf'))\n"
        "excludes=['tkinter']\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text("from backend.app.main import app\nuvicorn.run(app)\n", encoding="utf-8")
    (tmp_path / "setup_check.py").write_text("def install_playwright():\n    pass\n", encoding="utf-8")
    (tmp_path / "build_exe.bat").write_text("ISCC installer.iss\n", encoding="utf-8")

    findings = collect_release_findings(tmp_path)

    assert any("installer.iss 版本不一致" in f.message for f in findings)


def test_collect_release_findings_flags_locked_frameless_window(tmp_path: Path):
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "version.py").write_text('VERSION = "1.4.1"\n', encoding="utf-8")
    (tmp_path / "installer.iss").write_text('#define MyAppVersion "1.4.1"\n', encoding="utf-8")
    (tmp_path / "build.spec").write_text(
        "hiddenimports=['f2.apps.douyin.handler','playwright.async_api','webview.platforms.winforms']\n"
        "datas=[('conf.yaml', 'f2/conf'), ('cacert.pem', 'certifi')]\n"
        "excludes=[]\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text("from backend.app.main import app\nuvicorn.run(app)\n", encoding="utf-8")
    (tmp_path / "setup_check.py").write_text("def install_playwright():\n    pass\n", encoding="utf-8")
    (tmp_path / "build_exe.bat").write_text("ISCC installer.iss\n", encoding="utf-8")
    (tmp_path / "desktop_app.py").write_text(
        "webview.create_window(frameless=True, confirm_close=True)\n",
        encoding="utf-8",
    )

    findings = collect_release_findings(tmp_path)

    assert any("frameless=True" in f.message for f in findings)
    assert any("confirm_close=True" in f.message for f in findings)


def test_collect_release_findings_requires_installer_build_step(tmp_path: Path):
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "version.py").write_text('VERSION = "1.4.1"\n', encoding="utf-8")
    (tmp_path / "installer.iss").write_text(
        '#define MyAppVersion "1.4.1"\n'
        'OutputBaseFilename=Ptu_Setup_v{#MyAppVersion}\n'
        'Source: "dist\\Ptu\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs\n',
        encoding="utf-8",
    )
    (tmp_path / "build.spec").write_text(
        "hiddenimports=['f2.apps.douyin.handler','playwright.async_api','webview.platforms.winforms']\n"
        "datas=[('conf.yaml', 'f2/conf'), ('cacert.pem', 'certifi')]\n"
        "excludes=[]\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text("from backend.app.main import app\nuvicorn.run(app)\n", encoding="utf-8")
    (tmp_path / "desktop_app.py").write_text("webview.create_window(frameless=False, confirm_close=False)\n", encoding="utf-8")
    (tmp_path / "setup_check.py").write_text("def install_playwright():\n    pass\n", encoding="utf-8")
    (tmp_path / "build_exe.bat").write_text("pyinstaller build.spec\n", encoding="utf-8")

    findings = collect_release_findings(tmp_path)

    assert any("Inno Setup" in f.message for f in findings)


def test_collect_release_findings_passes_valid_v15_fixture(tmp_path: Path):
    _write_valid_release_fixture(tmp_path)

    findings = collect_release_findings(tmp_path)

    assert findings == []


def test_collect_release_findings_flags_clipboard_powershell_fallback(tmp_path: Path):
    _write_valid_release_fixture(tmp_path)
    (tmp_path / "backend" / "app" / "js_api.py").write_text(
        "class JsApi:\n"
        "    def get_clipboard(self):\n"
        "        return subprocess.run(['powershell', '-NoProfile', '-Command', 'Get-Clipboard -Raw']).stdout\n",
        encoding="utf-8",
    )

    findings = collect_release_findings(tmp_path)

    assert any("PowerShell" in f.message for f in findings)
