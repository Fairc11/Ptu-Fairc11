"""Profile scraping API routes."""
from fastapi import APIRouter, HTTPException
from ..models.schemas import ProfileResult

router = APIRouter(prefix="/api/profile", tags=["profile"])

# Lazy import to avoid circular dependency at module level
_scraper = None


def _get_scraper():
    global _scraper
    if _scraper is None:
        from ..services.scraper import DouyinScraper
        _scraper = DouyinScraper()
    return _scraper


@router.post("/scrape")
async def scrape_profile(data: dict):
    """抓取抖音用户主页的所有作品。"""
    url = data.get("url", "").strip()
    if not url:
        raise HTTPException(400, "请输入主页链接")
    max_posts = min(data.get("max_posts", 50), 200)
    try:
        scraper = _get_scraper()
        result = await scraper.scrape_profile(url, max_posts=max_posts)
        return result.model_dump(mode="json")
    except Exception as e:
        raise HTTPException(500, f"主页抓取失败: {str(e)[:200]}")
