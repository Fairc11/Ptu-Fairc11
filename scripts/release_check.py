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


def _get_function_source(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    return ""


def collect_release_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []

    version_file = root / "backend" / "app" / "version.py"
    installer_file = root / "installer.iss"
    build_spec = root / "build.spec"
    build_bat = root / "build_exe.bat"
    run_py = root / "run.py"
    desktop_app = root / "desktop_app.py"
    setup_check = root / "setup_check.py"
    js_api = root / "backend" / "app" / "js_api.py"
    native_douyin_panel = root / "backend" / "app" / "desktop_douyin_panel.py"
    app_js = root / "backend" / "app" / "static" / "js" / "app.js"
    index_html = root / "backend" / "app" / "templates" / "index.html"
    main_py = root / "backend" / "app" / "main.py"
    media_processor = root / "backend" / "app" / "services" / "media_processor.py"
    qr_login = root / "backend" / "app" / "services" / "qr_login.py"
    router_profile = root / "backend" / "app" / "api" / "router_profile.py"

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

    if js_api.exists():
        get_clipboard_source = _get_function_source(js_api, "get_clipboard")
        if "powershell" in get_clipboard_source.lower() or "Get-Clipboard -Raw" in get_clipboard_source:
            findings.append(Finding("error", "js_api.py 的 get_clipboard 不应使用 PowerShell，否则粘贴按钮会闪命令行窗口"))
        js_api_text = js_api.read_text(encoding="utf-8")
        if "open_douyin_panel" not in js_api_text or "mount_douyin_panel" not in js_api_text or "resize_douyin_panel" not in js_api_text:
            findings.append(Finding("error", "js_api.py 必须提供主窗口内嵌抖音 WebView2 挂载、缩放和打开桥接"))
        if "copy_douyin_panel_url" in js_api_text:
            findings.append(Finding("error", "js_api.py 不应再提供复制当前抖音链接桥接，v1.5 体验优化改为用户手动复制教程"))
        open_panel_source = _get_function_source(js_api, "open_douyin_panel")
        if "webview.create_window" in open_panel_source:
            findings.append(Finding("error", "open_douyin_panel 不得再创建第二个顶层窗口，必须挂载到主窗口右侧内置区"))

    native_panel_text = native_douyin_panel.read_text(encoding="utf-8") if native_douyin_panel.exists() else ""
    if "WebView2" not in native_panel_text or "self._form.Controls.Add(webview)" not in native_panel_text:
        findings.append(Finding("error", "desktop_douyin_panel.py 必须创建主窗口内的 WebView2 子控件"))
    if "NewWindowRequested" not in native_panel_text or "args.Handled = True" not in native_panel_text:
        findings.append(Finding("error", "右侧抖音内嵌 WebView 必须拦截新窗口请求并在当前控件内导航"))

    app_js_text = app_js.read_text(encoding="utf-8") if app_js.exists() else ""
    if "max_posts: 500" in app_js_text:
        findings.append(Finding("error", "主页抓取前端不应一次请求 500 个作品，v1.5 必须按 30 个分页主动加载"))
    if "max_cursor: state.profileNextCursor" not in app_js_text:
        findings.append(Finding("error", "主页抓取必须支持下一批分页加载，不能只停在前 30 个"))
    if "openDouyinPanel" not in app_js_text or "mountBrowserDock" not in app_js_text:
        findings.append(Finding("error", "app.js 必须接入右侧内嵌抖音预览，并随右侧宿主区域挂载/缩放"))
    if "copyBrowserUrl" in app_js_text:
        findings.append(Finding("error", "app.js 不应再提供复制当前链接按钮逻辑，必须改为手动复制教程"))
    if "useBrowserUrlAsSingle" in app_js_text or "useBrowserUrlAsProfile" in app_js_text:
        findings.append(Finding("error", "app.js 不应再自动把抖音当前状态 URL 填到左侧，避免 modal_id/self 链接误抓"))

    index_text = index_html.read_text(encoding="utf-8") if index_html.exists() else ""
    if 'id="browser-dock"' not in index_text or 'id="browser-native-host"' not in index_text or 'id="tab-browser"' in index_text or 'data-tab="browser"' in index_text:
        findings.append(Finding("error", "index.html 必须使用主界面右侧抖音预览 Dock，不应保留左侧内置浏览模式入口"))
    if 'id="login-modal"' in index_text or 'id="browser-login-panel"' not in index_text:
        findings.append(Finding("error", "扫码登录必须在右侧内置浏览区内联展示，不应再使用居中登录弹窗"))
    if "复制当前链接" in index_text:
        findings.append(Finding("error", "右侧抖音预览不应再提供复制当前链接按钮，避免复制到状态链接"))
    if "不自动扫描页面" not in index_text or "不自动翻页" not in index_text:
        findings.append(Finding("error", "内置抖音浏览面板必须在界面写明低风险边界：不自动扫描页面、不自动翻页"))
    if 'id="disclaimer-modal"' not in index_text or "同意并进入" not in index_text:
        findings.append(Finding("error", "index.html 必须提供首次使用免责声明和同意入口"))

    router_profile_text = router_profile.read_text(encoding="utf-8") if router_profile.exists() else ""
    if "MAX_PROFILE_POSTS = 30" not in router_profile_text:
        findings.append(Finding("error", "router_profile.py 必须将主页抓取/批量下载单次上限限制为 30"))

    main_text = main_py.read_text(encoding="utf-8") if main_py.exists() else ""
    if "/api/logs/diagnostic" not in main_text or "[REDACTED]" not in main_text:
        findings.append(Finding("error", "main.py 必须提供脱敏诊断包导出，朋友机器排障不能导出真实 cookie"))

    media_text = media_processor.read_text(encoding="utf-8") if media_processor.exists() else ""
    if "CREATE_NO_WINDOW" not in media_text or 'encoding": "utf-8"' not in media_text or 'errors": "replace"' not in media_text:
        findings.append(Finding("error", "media_processor.py 的 FFmpeg/ffprobe 子进程必须隐藏窗口并使用 UTF-8 容错解码"))
    if "xfade=transition=wipeleft" not in media_text:
        findings.append(Finding("error", "media_processor.py 必须内置无绿边的抖音式横向翻页 preset"))

    qr_text = qr_login.read_text(encoding="utf-8") if qr_login.exists() else ""
    if 'channel="msedge"' in qr_text or "系统 Edge" in qr_text:
        findings.append(Finding("error", "qr_login.py 不应把用户系统 Edge 作为二维码兜底正常路径，必须使用 Ptu 内置隔离浏览器"))
    if "executable_path=exe_path" not in qr_text or "使用内置 Chromium" not in qr_text:
        findings.append(Finding("error", "qr_login.py 二维码兜底必须优先使用 Ptu 内置 Chromium/headless shell"))
    if '"--headless=new"' not in qr_text or '"--window-position=-32000,-32000"' not in qr_text:
        findings.append(Finding("error", "qr_login.py 二维码浏览器兜底必须强制后台/离屏运行，不能弹出抖音浏览器窗口"))

    spec_text = build_spec.read_text(encoding="utf-8") if build_spec.exists() else ""
    required_hidden = [
        "f2.apps.douyin.handler",
        "playwright.async_api",
        "webview.platforms.winforms",
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
    if (
        "vendor' / 'ffmpeg' / 'ffmpeg.exe" not in spec_text
        and 'vendor" / "ffmpeg" / "ffmpeg.exe' not in spec_text
    ):
        findings.append(Finding("error", "build.spec 必须内置 vendor/ffmpeg/ffmpeg.exe，确保小白用户无需安装 FFmpeg"))
    if "_copy_to_dist_root(_vendor_ffmpeg)" not in spec_text:
        findings.append(Finding("error", "build.spec 必须把 ffmpeg.exe 复制到 Ptu.exe 同级目录，封包运行时才能优先命中内置 FFmpeg"))
    if (
        "vendor' / 'ffmpeg' / 'ffprobe.exe" not in spec_text
        and 'vendor" / "ffmpeg" / "ffprobe.exe' not in spec_text
    ):
        findings.append(Finding("error", "build.spec 必须内置 vendor/ffmpeg/ffprobe.exe，确保实况成片可探测音乐时长"))
    if "_copy_to_dist_root(_vendor_ffprobe)" not in spec_text:
        findings.append(Finding("error", "build.spec 必须把 ffprobe.exe 复制到 Ptu.exe 同级目录，音乐时长探测才能跟随内置 FFmpeg"))
    if "_copy_to_dist_root(_third_party_notices)" not in spec_text:
        findings.append(Finding("error", "build.spec 必须把 THIRD_PARTY_NOTICES.md 复制到 dist，随安装包提供第三方说明"))
    if "chromium_headless_shell-*" not in spec_text or "chrome-headless-shell.exe" not in spec_text:
        findings.append(Finding("error", "build.spec 必须自动收集可用的 Playwright Chromium headless shell，确保小白用户零前置"))

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
