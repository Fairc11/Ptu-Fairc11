from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def read_project_version(version_file: Path) -> str:
    text = version_file.read_text(encoding="utf-8")
    m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        raise ValueError(f"未找到 VERSION: {version_file}")
    return m.group(1)


def _count_function_defs(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(isinstance(node, ast.FunctionDef) and node.name == name for node in ast.walk(tree))


def collect_release_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []

    version_file = root / "backend" / "app" / "version.py"
    installer_file = root / "installer.iss"
    build_spec = root / "build.spec"
    build_bat = root / "build_exe.bat"
    run_py = root / "run.py"
    desktop_app = root / "desktop_app.py"
    setup_check = root / "setup_check.py"

    version = read_project_version(version_file)

    installer_text = installer_file.read_text(encoding="utf-8") if installer_file.exists() else ""
    installer_match = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', installer_text)
    if not installer_match:
        findings.append(Finding("error", "installer.iss 缺少 MyAppVersion"))
    elif installer_match.group(1) != version:
        findings.append(Finding("error", f"installer.iss 版本不一致: {installer_match.group(1)} != {version}"))
    if "Source: \"dist\\Ptu\\*\"" not in installer_text:
        findings.append(Finding("error", "installer.iss 必须复制 dist\\Ptu\\*，对外生成单EXE安装包但内部保持 onedir"))
    if f"OutputBaseFilename=Ptu_Setup_v{{#MyAppVersion}}" not in installer_text:
        findings.append(Finding("error", "installer.iss 输出文件名应为 Ptu_Setup_v{version}.exe 格式"))

    build_bat_text = build_bat.read_text(encoding="utf-8") if build_bat.exists() else ""
    if "ISCC" not in build_bat_text or "installer.iss" not in build_bat_text:
        findings.append(Finding("error", "build_exe.bat 必须调用 Inno Setup 生成单EXE安装包"))
    if "Ptu_v1.4.1.zip" in build_bat_text or "tar -a -c" in build_bat_text:
        findings.append(Finding("error", "build_exe.bat 不应再提示 ZIP 分发，默认产物应是 installer\\Ptu_Setup_v{version}.exe"))

    run_text = run_py.read_text(encoding="utf-8") if run_py.exists() else ""
    if 'uvicorn.run("backend.app.main:app"' in run_text or "uvicorn.run('backend.app.main:app'" in run_text:
        findings.append(Finding("error", "run.py 使用 uvicorn 字符串导入，封包后可能失效"))
    if "if sys.stdout" not in run_text and "sys.stdout.write" in run_text:
        findings.append(Finding("error", "run.py 写 stdout 前缺少 None 保护"))

    desktop_text = desktop_app.read_text(encoding="utf-8") if desktop_app.exists() else ""
    if re.search(r"frameless\s*=\s*True", desktop_text):
        findings.append(Finding("error", "desktop_app.py 不应使用 frameless=True，原生窗口才能稳定拖拽缩放和关闭"))
    if re.search(r"confirm_close\s*=\s*True", desktop_text):
        findings.append(Finding("error", "desktop_app.py 不应启用 confirm_close=True，右上角关闭应直接退出"))

    if setup_check.exists() and _count_function_defs(setup_check, "install_playwright") != 1:
        findings.append(Finding("error", "setup_check.py 中 install_playwright 必须且只能定义一次"))

    spec_text = build_spec.read_text(encoding="utf-8") if build_spec.exists() else ""
    required_hidden = [
        "f2.apps.douyin.handler",
        "playwright.async_api",
        "webview.platforms.winforms",
        "browser_cookie3",
    ]
    for item in required_hidden:
        if item not in spec_text:
            findings.append(Finding("error", f"build.spec hiddenimports 缺少 {item}"))
    if "f2/conf" not in spec_text:
        findings.append(Finding("error", "build.spec datas 缺少 f2/conf 配置文件收集"))
    if "certifi" not in spec_text:
        findings.append(Finding("error", "build.spec datas 缺少 certifi 证书收集"))
    if re.search(r"excludes\s*=.*['\"]cryptography['\"]", spec_text, re.S):
        findings.append(Finding("error", "build.spec 不应排除 cryptography，可能影响 f2 加密签名"))

    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = collect_release_findings(root)
    if not findings:
        print("[OK] 发布检查通过")
        return 0
    for finding in findings:
        print(f"[{finding.level.upper()}] {finding.message}")
    return 1 if any(f.level == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
