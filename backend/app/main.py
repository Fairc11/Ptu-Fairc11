from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import settings
from .models.task_store import TaskStore, store as task_store_ref
from .api import router_scraper, router_download, router_media, router_ws, router_login

app = FastAPI(title="Ptu", version="1.0.0")


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


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router_scraper.router)
app.include_router(router_download.router)
app.include_router(router_media.router)
app.include_router(router_ws.router)
app.include_router(router_login.router)

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
    html = _render("index.html", tasks=tasks)
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


@app.get("/api/tasks/{task_id}/output")
async def download_output(task_id: str):
    from .models.task_store import get_store
    from fastapi import HTTPException
    store = get_store()
    task = store.get(task_id)
    if not task or not task.output_path:
        raise HTTPException(404, "视频未找到，请先渲染")
    return FileResponse(task.output_path, filename="slideshow.mp4")
