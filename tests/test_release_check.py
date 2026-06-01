from __future__ import annotations

from pathlib import Path

from scripts.release_check import collect_release_findings, read_project_version


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
        "hiddenimports=['f2.apps.douyin.handler','playwright.async_api','webview.platforms.winforms','browser_cookie3']\n"
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
        "hiddenimports=['f2.apps.douyin.handler','playwright.async_api','webview.platforms.winforms','browser_cookie3']\n"
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
