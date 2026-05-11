from pathlib import Path
import httpx
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from .config import settings
from .models.task_store import TaskStore, store as task_store_ref
from .api import router_scraper, router_download, router_media, router_ws, router_login

# 共享 httpx 客户端（复用连接池）
_proxy_client = httpx.AsyncClient(
    follow_redirects=True, timeout=60.0,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.douyin.com/",
    }
)

app = FastAPI(title="Ptu", version="1.2.0")


@app.on_event("startup")
async def startup():
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
    t = jinja_env.get_template(name)
    return t.render(**kwargs, static_url="/static")


@app.get("/")
async def index(request: Request):
    from .models.task_store import get_store
    store = get_store()
    tasks = store.list_tasks()
    desktop_mode = request.query_params.get("desktop", "false").lower() in ("true", "1")
    html = _render("index.html", tasks=tasks, desktop_mode=desktop_mode)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html)


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
    return task


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
        folders.append(task.output_path)
    if not folders:
        if dl.exists():
            folders.append(str(dl))
        if out.exists():
            folders.append(str(out))
    if not folders:
        raise HTTPException(404, "未找到文件")
    import subprocess
    for f in folders:
        subprocess.Popen(["explorer", f], shell=True)
    return {"opened": folders}


@app.get("/api/tasks/{task_id}/output")
async def download_output(task_id: str):
    from .models.task_store import get_store
    from fastapi import HTTPException
    store = get_store()
    task = store.get(task_id)
    if not task or not task.output_path:
        raise HTTPException(404, "视频未找到，请先渲染")
    return FileResponse(task.output_path, filename="slideshow.mp4")


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
