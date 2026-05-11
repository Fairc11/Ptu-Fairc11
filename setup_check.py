"""
Ptu - 环境检测与自动安装模块。

打包后的 exe 首次运行时检测缺失组件并自动下载。
"""
from __future__ import annotations
import os
import sys
import shutil
import subprocess
from pathlib import Path


def _print_box(title: str, lines: list[str]):
    """打印带框文字."""
    width = max(len(l) for l in lines) if lines else 40
    width = max(width + 4, 50)
    print("┌" + "─" * (width - 2) + "┐")
    print(f"│ {title:^{width-4}} │")
    print("├" + "─" * (width - 2) + "┤")
    for l in lines:
        print(f"│ {l:<{width-4}} │")
    print("└" + "─" * (width - 2) + "┘")


def _run_cmd(cmd: list[str], desc: str = "") -> tuple[int, str]:
    """运行命令并返回 (返回码, 输出)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout + r.stderr
    except FileNotFoundError:
        return -1, f"未找到命令: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "超时"
    except Exception as e:
        return -3, str(e)


def _get_playwright_browsers_dir() -> Path:
    """获取 Playwright 浏览器安装目录。"""
    home = Path.home()
    # Windows 上 playwright 将浏览器安装在 %USERPROFILE%\AppData\Local\ms-playwright\
    candidates = [
        home / "AppData" / "Local" / "ms-playwright",
        home / ".playwright",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def get_chromium_path() -> str | None:
    """查找已安装的 Playwright Chromium/headless-shell 可执行文件路径。"""
    browsers_dir = _get_playwright_browsers_dir()
    if not browsers_dir.exists():
        return None
    for item in browsers_dir.iterdir():
        name = item.name.lower()
        if item.is_dir() and ("chromium" in name or "chrome" in name):
            for exe in ["chrome.exe", "chromium.exe", "chromium-headless-shell.exe"]:
                found = list(item.rglob(exe))
                if found:
                    return str(found[0])
    return None


def check_playwright() -> bool:
    """检查 Playwright Chromium 是否已安装。"""
    return get_chromium_path() is not None


def _get_chromium_build_id() -> str | None:
    """从 Playwright 内部获取 Chromium headless shell 的 build ID。"""
    # 方式一：通过 playwright 内部 registry
    try:
        from playwright._impl._registry import ALL_BROWSERS
        for b in ALL_BROWSERS:
            name = b.name.lower()
            if "headless" in name and "chromium" in name:
                return str(b.revision)
    except Exception:
        pass
    # 方式二：从 browsers.json 读取
    try:
        import json
        import playwright
        pw_dir = Path(playwright.__file__).parent
        bj = pw_dir / "driver" / "package" / "browsers.json"
        if bj.exists():
            data = json.loads(bj.read_text("utf-8"))
            for b in data.get("browsers", []):
                if "headless" in b.get("name", "") and "chromium" in b.get("name", ""):
                    return str(b["revision"])
    except Exception:
        pass
    return None


def install_chromium_direct() -> bool:
    """直接下载 Chromium headless shell（支持 PyInstaller 打包环境）。"""
    import urllib.request
    import zipfile
    import io

    build_id = _get_chromium_build_id()
    if not build_id:
        print("[!] 无法确定 Chromium 版本号，请手动安装: python -m playwright install chromium-headless-shell")
        return False

    dest_dir = (_get_playwright_browsers_dir()
                / f"chromium_headless_shell-{build_id}"
                / "chrome-headless-shell-win64")
    exe_path = dest_dir / "headless_shell.exe"

    if exe_path.exists():
        print("[OK] Chromium 已存在")
        return True

    url = (f"https://playwright.azureedge.net/builds/chromium-headless-shell/"
           f"{build_id}/chromium-headless-shell-win64.zip")

    print()
    _print_box("下载 Chromium 浏览器引擎（约 150MB）", [
        "正在从 Playwright CDN 下载...",
        "下载完成后自动解压安装",
    ])
    print()

    try:
        print(f"[*] 下载: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=300)
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunks = []

        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 // total
                print(f"\r  下载中... {pct}% ({downloaded//1024//1024}MB"
                      f"/{total//1024//1024}MB)", end="")

        print("\r  下载完成，正在解压...       ")
        data = b"".join(chunks)

        dest_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith(".exe") or name.endswith(".dll") or name.endswith(".pak"):
                    out_name = Path(name).name
                    if out_name:
                        with zf.open(name) as f_in:
                            (dest_dir / out_name).write_bytes(f_in.read())

        if exe_path.exists():
            print(f"[OK] Chromium 安装完成: {exe_path}")
            return True
        else:
            print(f"[!] 解压后未找到 headless_shell.exe")
            return False
    except Exception as e:
        print(f"[!] 下载失败: {e}")
        return False


def install_playwright():
    """自动安装 Playwright Chromium。"""
    print()
    _print_box("安装 Chromium 浏览器引擎", [
        "Ptu 需要 Chromium 来抓取抖音内容",
        "正在下载（约 150MB），请稍候...",
        "下载完成后会自动解压安装",
    ])
    print()

    # 打包环境下 subprocess 不可用，直接走下载
    if getattr(sys, 'frozen', False):
        return install_chromium_direct()

    try:
        import playwright
        print(f"[*] 正在安装 Chromium headless shell...")

        code, out = _run_cmd(
            [sys.executable, "-m", "playwright", "install", "chromium-headless-shell"],
            desc="安装 Chromium"
        )

        if code == 0:
            print("[OK] Chromium 安装完成")
            return True
        else:
            print(f"[!] subprocess 安装失败: {out[:200]}")
            print("[*] 尝试直接下载...")
            return install_chromium_direct()
    except Exception as e:
        print(f"[!] 安装过程出错: {e}")
        return install_chromium_direct()


def check_ffmpeg() -> bool:
    """检查 FFmpeg 是否可用。"""
    # 检查当前目录
    if (Path("ffmpeg.exe")).exists():
        return True
    if (Path("ffmpeg")).exists():
        return True
    # 检查 PATH
    code, _ = _run_cmd(["ffmpeg", "-version"])
    return code == 0


def install_playwright():
    """自动安装 Playwright Chromium。"""
    print()
    _print_box("安装 Chromium 浏览器引擎", [
        "Ptu 需要 Chromium 来抓取抖音内容",
        "正在下载（约 150MB），请稍候...",
        "下载完成后会自动解压安装",
    ])
    print()

    try:
        import playwright
        pw_dir = Path(playwright.__file__).parent
        print(f"[*] 正在安装 Chromium headless shell...")

        code, out = _run_cmd(
            [sys.executable, "-m", "playwright", "install", "chromium-headless-shell"],
            desc="安装 Chromium"
        )

        if code == 0:
            print("[OK] Chromium 安装完成")
            return True
        else:
            print(f"[!] 安装失败: {out[:200]}")
            print("[*] 尝试备用方法...")
            # 备用: 直接 pip install playwright 然后重试
            _run_cmd([sys.executable, "-m", "pip", "install", "playwright"])
            code2, out2 = _run_cmd([sys.executable, "-m", "playwright", "install", "chromium-headless-shell"])
            if code2 == 0:
                print("[OK] Chromium 安装完成")
                return True
            print(f"[!] 备用方法也失败: {out2[:200]}")
            return False
    except Exception as e:
        print(f"[!] 安装过程出错: {e}")
        return False


def install_ffmpeg():
    """自动下载 FFmpeg。"""
    print()
    _print_box("安装 FFmpeg", [
        "Ptu 需要 FFmpeg 来处理视频",
        "正在下载（约 50MB），请稍候...",
    ])
    print()

    import urllib.request
    import zipfile
    import io

    # FFmpeg Windows 下载地址
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

    try:
        print("[*] 正在下载 FFmpeg...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=120)
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunks = []

        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 // total
                print(f"\r  下载中... {pct}% ({downloaded//1024//1024}MB/{total//1024//1024}MB)", end="")

        print("\r  下载完成，正在解压...")
        data = b"".join(chunks)

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith("ffmpeg.exe"):
                    with zf.open(name) as f:
                        with open("ffmpeg.exe", "wb") as out:
                            out.write(f.read())
                    break

        print("[OK] FFmpeg 安装完成")
        return True
    except Exception as e:
        print(f"[!] FFmpeg 下载失败: {e}")
        print("[*] 你可以手动下载 ffmpeg.exe 放到程序目录")
        return False


def run_setup():
    """运行环境检测和安装。"""
    print()
    _print_box("Ptu - 环境检测", [
        "正在检查运行所需组件...",
    ])
    print()

    results = []

    # 检测 Chromium
    print("[*] 检查 Chromium... ", end="")
    if check_playwright():
        print("已就绪 [OK]")
        results.append(("Chromium", True))
    else:
        print("未安装")
        results.append(("Chromium", False))

    # 检测 FFmpeg
    print("[*] 检查 FFmpeg... ", end="")
    if check_ffmpeg():
        print("已就绪 [OK]")
        results.append(("FFmpeg", True))
    else:
        print("未安装")
        results.append(("FFmpeg", False))

    # 安装缺失组件
    any_missing = False
    for name, ok in results:
        if not ok:
            any_missing = True
            print(f"\n[*] 需要安装: {name}")
            if name == "Chromium":
                install_playwright()
            elif name == "FFmpeg":
                install_ffmpeg()

    # 最终检查
    print()
    all_ok = True
    for name, _ in results:
        check_fn = check_playwright if name == "Chromium" else check_ffmpeg
        ok = check_fn()
        status = "[OK]" if ok else "[FAIL]"
        print(f"  {name}: {status}")
        if not ok:
            all_ok = False

    return all_ok


def quick_check():
    """快速检测，不阻塞启动，只打印提醒。"""
    if not check_playwright():
        print("[*] Chromium 未安装，将在启动后自动下载")
    if not check_ffmpeg():
        print("[*] FFmpeg 未安装，渲染视频功能将不可用")


if __name__ == "__main__":
    run_setup()
