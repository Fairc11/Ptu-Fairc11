from fastapi import APIRouter, HTTPException
from ..models.schemas import ScrapeRequest, ScrapeResponse, TaskStatus
from ..models.task_store import get_store
from ..services.scraper import DouyinScraper

router = APIRouter(prefix="/api", tags=["scraper"])

scraper = DouyinScraper()


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_douyin(req: ScrapeRequest):
    """Parse a douyin share link and return content metadata."""
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "请输入链接")

    store = get_store()
    task = store.create(url)

    try:
        store.update_status(task.task_id, TaskStatus.SCRAPING)
        metadata = await scraper.scrape(url)
        store.update_metadata(task.task_id, metadata)
        store.update_status(task.task_id, TaskStatus.SCRAPED)

        if not metadata.image_urls:
            raise HTTPException(400, "未找到图片内容，请确认链接是图文/笔记")

        return ScrapeResponse(task_id=task.task_id, metadata=metadata)

    except HTTPException:
        raise
    except PermissionError as e:
        store.update_status(task.task_id, TaskStatus.ERROR, error_message=str(e))
        raise HTTPException(401, str(e))
    except ConnectionError as e:
        store.update_status(task.task_id, TaskStatus.ERROR, error_message=str(e))
        raise HTTPException(401, str(e))
    except Exception as e:
        store.update_status(task.task_id, TaskStatus.ERROR, error_message=str(e))
        raise HTTPException(500, f"抓取失败: {str(e)}")
