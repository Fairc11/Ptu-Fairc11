"""Profile scraping API routes."""
from fastapi import APIRouter, HTTPException
from ..models.schemas import LivePhotoSource, MediaType, ProfileResult, ScrapeResult, TaskStatus

router = APIRouter(prefix="/api/profile", tags=["profile"])
MAX_PROFILE_POSTS = 30

# Lazy import to avoid circular dependency at module level
_scraper = None


def _get_scraper():
    global _scraper
    if _scraper is None:
        from ..services.scraper import DouyinScraper
        _scraper = DouyinScraper()
    return _scraper


def _result_from_profile_post(post: dict, user_name: str) -> ScrapeResult | None:
    """Build a download-ready result from fields already returned by profile API."""
    desc = post.get("desc", "") or ""
    media_type = post.get("media_type", "")
    image_urls = [u for u in (post.get("image_urls") or []) if isinstance(u, str) and u]
    video_url = post.get("video_url", "") or ""
    music_url = post.get("music_url", "") or ""
    music_title = post.get("music_title", "") or ""
    cover_url = post.get("cover_url", "") or (image_urls[0] if image_urls else "")
    create_time = post.get("create_time", 0) or 0
    aweme_id = post.get("aweme_id", "") or ""

    if media_type == "video" and video_url:
        return ScrapeResult(
            title=desc,
            author=user_name,
            media_type=MediaType.VIDEO,
            image_urls=[cover_url] if cover_url else [],
            music_url=video_url,
            music_title=music_title,
            aweme_id=aweme_id,
            create_time=create_time,
            text_content=desc,
        )

    if image_urls:
        raw_live = post.get("live_photo_data") or []
        live_data = [
            LivePhotoSource(image_url=item.get("image_url", ""), video_url=item.get("video_url", ""))
            for item in raw_live
            if isinstance(item, dict) and item.get("image_url")
        ]
        has_any_video = any(item.video_url for item in live_data)
        all_have_video = all(item.video_url for item in live_data) if live_data else False
        if has_any_video and not all_have_video:
            result_type = MediaType.COMPREHENSIVE
        elif has_any_video:
            result_type = MediaType.LIVE_PHOTO
        else:
            result_type = MediaType.IMAGE_SET
        return ScrapeResult(
            title=desc,
            author=user_name,
            media_type=result_type,
            image_urls=image_urls,
            live_photo_data=live_data,
            music_url=music_url or None,
            music_title=music_title,
            cover_url=cover_url or None,
            aweme_id=aweme_id,
            create_time=create_time,
            text_content=desc,
        )

    return None


@router.post("/scrape")
async def scrape_profile(data: dict):
    """抓取抖音用户主页的所有作品。支持主页链接和分享链接。"""
    url = data.get("url", "").strip()
    if not url:
        raise HTTPException(400, "请输入主页链接")
    max_posts = min(int(data.get("max_posts", MAX_PROFILE_POSTS)), MAX_PROFILE_POSTS)
    max_cursor = int(data.get("max_cursor", 0) or 0)
    try:
        scraper = _get_scraper()
        result = await scraper.scrape_profile(url, max_posts=max_posts, max_cursor=max_cursor)
        return result.model_dump(mode="json")
    except Exception as e:
        raise HTTPException(500, f"主页抓取失败: {str(e)[:200]}")


@router.post("/batch-download")
async def batch_download(data: dict):
    """批量抓取并下载主页选中的作品。"""
    import uuid
    from datetime import datetime
    from pathlib import Path
    from ..config import settings
    from ..services.downloader import download_manager
    from ..services.progress import progress_emitter

    posts = data.get("posts", [])
    if not posts:
        raise HTTPException(400, "请选择要下载的作品")
    if len(posts) > MAX_PROFILE_POSTS:
        raise HTTPException(400, f"单次最多下载 {MAX_PROFILE_POSTS} 个作品，请减少选择数量")

    batch_id = uuid.uuid4().hex[:12]
    user_name = data.get("user_name", "未知用户")
    total = len(posts)
    results = []

    # 创建批量下载根目录
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_name = "".join(c for c in user_name if c.isalnum() or c in " _-")[:20]
    base_dir = settings.download_dir / f"{date_str}_{safe_name}_{batch_id[:8]}"
    base_dir.mkdir(parents=True, exist_ok=True)

    scraper = _get_scraper()

    for i, post in enumerate(posts):
        share_url = post.get("share_url", "")
        aweme_id = post.get("aweme_id", "")
        desc = post.get("desc", "")

        # 推送进度
        await progress_emitter.emit_stage(
            batch_id, "batch_downloading",
            i / max(total, 1),
            f"正在下载 {i+1}/{total}: {desc[:20]}",
            i + 1, total
        )

        # 子目录名：序号 + 简短描述
        post_dir_name = f"{i+1:03d}_{safe_name}"[:40]
        post_dir = base_dir / post_dir_name

        try:
            # 1) 优先使用主页接口已返回的下载字段；缺字段时再走旧的详情抓取兜底。
            result = _result_from_profile_post(post, user_name)
            if result is None:
                result = await scraper.scrape(share_url)
            if not result or not (result.image_urls or result.music_url):
                results.append({"index": i + 1, "desc": desc, "status": "empty"})
                continue

            # 2) 下载素材
            download_result = await download_manager.download_all(
                batch_id + f"_{i}", result, post_dir
            )
            has_downloaded_file = bool(
                download_result.get("video_path")
                or download_result.get("music_path")
                or download_result.get("images")
                or download_result.get("live_photo_videos")
                or download_result.get("live_photo_synths")
            )
            if not has_downloaded_file:
                results.append({"index": i + 1, "desc": desc, "status": "error",
                                "error": "下载未生成任何文件"})
                continue
            results.append({"index": i + 1, "desc": desc, "status": "ok"})
        except Exception as e:
            results.append({"index": i + 1, "desc": desc, "status": "error",
                            "error": str(e)[:100]})

    # 完成
    await progress_emitter.emit_stage(
        batch_id, "batch_complete", 1.0,
        f"全部完成: {total} 个作品", total, total
    )

    success = sum(1 for r in results if r["status"] == "ok")
    return {
        "batch_id": batch_id,
        "base_dir": str(base_dir),
        "total": total,
        "success": success,
        "results": results,
    }
