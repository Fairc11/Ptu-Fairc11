from pathlib import Path
import httpx
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from .config import settings
from .version import VERSION
from .log_config import setup_logging
from .models.task_store import TaskStore, store as task_store_ref
from .api import router_scraper, router_download, router_media, router_ws, router_login, router_profile

# 共享 httpx 客户端（复用连接池）
_proxy_client = httpx.AsyncClient(
    follow_redirects=True, timeout=60.0,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.douyin.com/",
    }
)

app = FastAPI(title="Ptu", version=VERSION)

# 热重载：每次服务器启动生成唯一 ID，前端轮询检测变化自动刷新
_build_id = str(__import__('time').time())


@app.on_event("startup")
async def startup():
    setup_logging(debug=settings.debug)
    db_path = settings.tasks_db
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = TaskStore(db_path)
    from backend.app.models import task_store as ts
    ts.store = store
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)


@app.on_event("shutdown")
async def shutdown():
    from .services.downloader import download_manager
    await download_manager.close()
    await _proxy_client.aclose()


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router_scraper.router)
app.include_router(router_download.router)
app.include_router(router_media.router)
app.include_router(router_ws.router)
app.include_router(router_login.router)
app.include_router(router_profile.router)


# ── CDN 代理（解决在线预览防盗链问题） ─────────────────────
ALLOWED_PROXY_DOMAINS = ["douyinpic.com", "tos-cn-", "zjcdn.com", "ies-music", "music.douyin"]


@app.get("/api/proxy/media")
async def proxy_media(url: str):
    """代理抖音 CDN 资源，加上正确 Referer 头绕过防盗链。"""
    if not any(d in url for d in ALLOWED_PROXY_DOMAINS):
        from fastapi import HTTPException
        raise HTTPException(403, "不允许的域名")
    try:
        resp = await _proxy_client.get(url)
        content_type = resp.headers.get("content-type", "application/octet-stream")
        return Response(content=resp.content, media_type=content_type)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(502, f"代理请求失败: {str(e)[:100]}")


from jinja2 import Environment, FileSystemLoader, select_autoescape

templates_dir = Path(__file__).parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render(name: str, **kwargs):
    import time
    t = jinja_env.get_template(name)
    return t.render(**kwargs, static_url="/static", cache_buster=str(int(time.time())))


@app.get("/")
async def index(request: Request):
    from .models.task_store import get_store
    store = get_store()
    tasks = store.list_tasks()
    desktop_mode = request.query_params.get("desktop", "false").lower() in ("true", "1")
    html = _render("index.html", tasks=tasks, desktop_mode=desktop_mode, version=VERSION)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


@app.get("/api/tasks")
async def list_tasks():
    from .models.task_store import get_store
    store = get_store()
    tasks = store.list_tasks()
    return [{"task_id": t.task_id, "share_url": t.share_url, "status": t.status.value,
             "title": t.metadata.title if t.metadata else "",
             "image_count": len(t.metadata.image_urls) if t.metadata else 0,
             "created_at": t.created_at.isoformat(),
             "error_message": t.error_message} for t in tasks]


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    from .models.task_store import get_store
    from fastapi import HTTPException
    store = get_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(404, "任务未找到")
    return task.model_dump(mode="json")


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    import shutil
    from .models.task_store import get_store
    from fastapi import HTTPException
    store = get_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(404, "任务未找到")
    dl = settings.download_dir / task_id
    if dl.exists():
        shutil.rmtree(dl)
    out = settings.output_dir / task_id
    if out.exists():
        shutil.rmtree(out)
    store.delete(task_id)
    return {"status": "deleted"}


@app.post("/api/tasks/batch-delete")
async def batch_delete(data: dict):
    import shutil
    from .models.task_store import get_store
    store = get_store()
    ids = data.get("task_ids", [])
    deleted = []
    for task_id in ids:
        task = store.get(task_id)
        if task:
            dl = settings.download_dir / task_id
            if dl.exists():
                shutil.rmtree(dl)
            out = settings.output_dir / task_id
            if out.exists():
                shutil.rmtree(out)
            store.delete(task_id)
            deleted.append(task_id)
    return {"deleted": deleted, "count": len(deleted)}


@app.get("/api/logs")
async def get_logs(lines: int = 100):
    """Return recent N lines from the log file."""
    from .log_config import LOG_DIR
    log_file = LOG_DIR / "ptu.log"
    if not log_file.exists():
        return {"lines": [], "total": 0}
    try:
        text = log_file.read_text("utf-8", errors="replace")
        all_lines = text.splitlines()
        recent = all_lines[-lines:]
        return {"lines": recent, "total": len(all_lines)}
    except Exception as e:
        return {"lines": [], "total": 0, "error": str(e)}


@app.get("/api/logs/files")
async def list_log_files():
    """列出 日志/runs/ 下自动保存的运行日志。"""
    from .log_config import RUNS_DIR, get_current_run_log
    files = []
    current = get_current_run_log()
    if RUNS_DIR.exists():
        for f in sorted(RUNS_DIR.glob("ptu_*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "date": f.stem.replace("ptu_", ""),
                "current": bool(current and f.resolve() == current.resolve()),
            })
    return {"files": files, "dir": str(RUNS_DIR)}


@app.get("/api/logs/export")
async def export_logs(file: str | None = None):
    """Download the current run log, or a selected historical log."""
    from .log_config import LOG_DIR, RUNS_DIR, EXPORTS_DIR, get_current_run_log
    from fastapi.responses import FileResponse
    if file:
        safe_name = Path(file).name
        candidates = [
            RUNS_DIR / safe_name,
            EXPORTS_DIR / safe_name,
            LOG_DIR / safe_name,
        ]
        log_file = next((p for p in candidates if p.exists() and p.is_file()), None)
    else:
        log_file = get_current_run_log()
        if not log_file or not log_file.exists():
            log_file = LOG_DIR / "ptu.log"
    if not log_file or not log_file.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "日志文件不存在")
    return FileResponse(str(log_file), filename=log_file.name)


@app.post("/api/logs/save")
async def save_logs():
    """保存当前运行日志快照到日志/exports/，返回路径。"""
    from .log_config import LOG_DIR, EXPORTS_DIR, get_current_run_log
    import shutil, datetime
    log_file = get_current_run_log()
    if not log_file or not log_file.exists():
        log_file = LOG_DIR / "ptu.log"
    if not log_file.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "日志文件不存在")
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    export_name = f"ptu_run_{ts}.log"
    export_path = EXPORTS_DIR / export_name
    shutil.copy2(str(log_file), str(export_path))
    return {"status": "ok", "path": str(export_path), "filename": export_name}


def _redact_diagnostic_text(text: str) -> str:
    import re
    patterns = [
        (r"(?i)(cookie|cookies|sessionid|sid_tt|sid_guard|odin_tt|msToken|passport_csrf_token)(['\"]?\s*[:=]\s*)[^,\s;]+", r"\1\2[REDACTED]"),
        (r"(?i)(Cookie:\s*)[^\n]+", r"\1[REDACTED]"),
    ]
    for pattern, repl in patterns:
        text = re.sub(pattern, repl, text)
    return text


SENSITIVE_DIAGNOSTIC_NAMES = {
    ".env",
    "cookies.yaml",
    "cookie.yaml",
    "cookies.json",
}


def _should_skip_diagnostic_file(path: Path) -> bool:
    name = path.name.lower()
    return name in SENSITIVE_DIAGNOSTIC_NAMES or name.endswith(".zip")


def _zip_tree(zf, root: Path, arc_root: str, *, redact_text: bool = False) -> None:
    if not root.exists():
        return
    if root.is_file():
        paths = [root]
        base = root.parent
    else:
        paths = [p for p in sorted(root.rglob("*")) if p.is_file()]
        base = root
    for path in paths:
        if _should_skip_diagnostic_file(path):
            continue
        rel = path.relative_to(base)
        arcname = str(Path(arc_root) / rel).replace("\\", "/")
        if redact_text or path.suffix.lower() in {".log", ".txt", ".json", ".yaml", ".yml"}:
            text = path.read_text("utf-8", errors="replace")
            zf.writestr(arcname, _redact_diagnostic_text(text))
        else:
            zf.write(path, arcname)


def _create_diagnostic_package() -> Path:
    """Create a redacted diagnostic zip with user-visible folders."""
    from .log_config import LOG_DIR, RUNS_DIR, EXPORTS_DIR, get_current_run_log
    import datetime
    import sys
    import zipfile

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = EXPORTS_DIR / f"ptu_diagnostic_{ts}.zip"

    chromium_path = ""
    try:
        from setup_check import get_chromium_path
        chromium_path = get_chromium_path() or ""
    except Exception as exc:
        chromium_path = f"检测失败: {exc}"

    ffmpeg_path = Path(settings.ffmpeg_path)
    ffprobe_name = "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe"
    ffprobe_path = ffmpeg_path.with_name(ffprobe_name) if ffmpeg_path.name else Path(ffprobe_name)
    cookies_path = Path(settings.cookies_path)
    cookies_exists = cookies_path.exists()
    diagnostic = "\n".join([
        f"Ptu version: {VERSION}",
        f"Python frozen: {bool(getattr(sys, 'frozen', False))}",
        f"Executable: {sys.executable}",
        f"Download dir: {settings.download_dir}",
        f"Output dir: {settings.output_dir}",
        f"Log dir: {LOG_DIR}",
        f"Chromium path: {chromium_path}",
        f"Chromium exists: {Path(chromium_path).exists() if chromium_path and not chromium_path.startswith('检测失败') else False}",
        f"FFmpeg path: {settings.ffmpeg_path}",
        f"FFmpeg exists: {ffmpeg_path.exists()}",
        f"FFprobe path: {ffprobe_path}",
        f"FFprobe exists: {ffprobe_path.exists()}",
        f"Cookies file exists: {cookies_exists}",
        "Cookies content: [REDACTED]",
    ])

    # Diagnostic packages favor speed and predictable copy/paste over compression ratio.
    # Media files are already compressed, so ZIP_STORED avoids long "exporting" waits.
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("diagnostic.txt", diagnostic)
        zf.writestr(
            "cookies_status.txt",
            "Ptu never exports raw Douyin cookies.\n"
            f"cookies.yaml exists: {cookies_exists}\n"
            "content: [REDACTED]\n",
        )
        _zip_tree(zf, settings.download_dir, "data/downloads")
        _zip_tree(zf, settings.output_dir, "data/output")
        _zip_tree(zf, settings.tasks_db, "data")
        _zip_tree(zf, LOG_DIR, "日志", redact_text=True)
        candidates = [LOG_DIR / "ptu.log", get_current_run_log()]
        if RUNS_DIR.exists():
            candidates.extend(sorted(RUNS_DIR.glob("ptu_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:3])
        seen = set()
        for path in candidates:
            if not path or not path.exists() or not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            text = path.read_text("utf-8", errors="replace")
            zf.writestr(f"logs/{path.name}", _redact_diagnostic_text(text))

    return zip_path


@app.get("/api/logs/diagnostic")
async def export_diagnostic_package():
    """导出脱敏诊断包，包含下载/输出/任务/日志，绝不包含真实 cookie。"""
    zip_path = _create_diagnostic_package()
    return FileResponse(str(zip_path), filename=zip_path.name, media_type="application/zip")


@app.post("/api/logs/diagnostic/create")
async def create_diagnostic_package():
    """Create a diagnostic zip and return its folder for the desktop UI."""
    zip_path = _create_diagnostic_package()
    return {
        "status": "ok",
        "path": str(zip_path),
        "folder": str(zip_path.parent),
        "filename": zip_path.name,
    }


@app.post("/api/logs/open-folder")
async def open_logs_folder():
    """Open the user-facing log folder in Explorer."""
    from .log_config import LOG_DIR
    import os
    import subprocess
    import sys

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(LOG_DIR))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(LOG_DIR)])
    else:
        subprocess.Popen(["xdg-open", str(LOG_DIR)])
    return {"status": "ok", "path": str(LOG_DIR)}


@app.get("/api/build-id")
async def build_id():
    """热重载：前端轮询此端点，ID 变化时自动刷新页面。"""
    from fastapi.responses import JSONResponse
    return JSONResponse({"id": _build_id}, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    })


@app.post("/api/browser/clear-cache")
async def clear_browser_cache():
    """清除浏览器缓存和登录状态。"""
    from .services.scraper import scraper as douyin_scraper
    from .services.qr_login import qr_service
    try:
        await qr_service.close()
        await douyin_scraper.clear_cache()
        return {"status": "ok", "message": "已清除 Ptu 保存的抖音登录痕迹"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/tasks/{task_id}/open-folder")
async def open_folder(task_id: str):
    from .models.task_store import get_store
    from fastapi import HTTPException
    store = get_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(404, "任务未找到")
    folders = []
    dl = settings.download_dir / task_id
    out = settings.output_dir / task_id
    # 优先使用 task 中存储的真实下载路径
    if task.download_path and Path(task.download_path).exists():
        folders.append(task.download_path)
    if task.output_path and Path(task.output_path).exists():
        output_path = Path(task.output_path)
        folders.append(str(output_path if output_path.is_dir() else output_path.parent))
    if not folders:
        if dl.exists():
            folders.append(str(dl))
        if out.exists():
            folders.append(str(out))
    if not folders:
        raise HTTPException(404, "未找到文件")
    import subprocess
    opened = []
    for f in dict.fromkeys(folders):
        folder = Path(f)
        if folder.is_file():
            folder = folder.parent
        import sys
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(folder)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        opened.append(str(folder))
    return {"opened": opened}


@app.get("/api/tasks/{task_id}/output")
async def download_output(task_id: str):
    from .models.task_store import get_store
    from fastapi import HTTPException
    store = get_store()
    task = store.get(task_id)
    if not task or not task.output_path:
        raise HTTPException(404, "视频未找到，请先渲染")
    return FileResponse(task.output_path, filename=Path(task.output_path).name)


@app.get("/api/tasks/{task_id}/files")
async def list_files(task_id: str):
    from .models.task_store import get_store
    from fastapi import HTTPException
    store = get_store()
    task = store.get(task_id)
    if not task or not task.download_path:
        raise HTTPException(404, "文件未找到")
    base = Path(task.download_path)
    files = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(base)
            files.append({"name": rel.name, "path": str(rel), "size": p.stat().st_size})
    return {"files": files, "base": str(base)}


@app.get("/api/tasks/{task_id}/files/{file_path:path}")
async def serve_file(task_id: str, file_path: str):
    from .models.task_store import get_store
    from fastapi import HTTPException
    store = get_store()
    task = store.get(task_id)
    if not task or not task.download_path:
        raise HTTPException(404, "任务未找到")
    full_path = Path(task.download_path) / file_path
    if not full_path.exists():
        raise HTTPException(404, "文件未找到")
    return FileResponse(str(full_path))
