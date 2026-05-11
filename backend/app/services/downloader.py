from __future__ import annotations
import asyncio
from pathlib import Path
import httpx
from ..config import settings
from ..models.schemas import ScrapeResult, MediaType
from .progress import progress_emitter


class DownloadManager:

    def __init__(self):
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                follow_redirects=True, timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.douyin.com/",
                }
            )
        return self._http_client

    async def download_all(self, task_id: str, metadata: ScrapeResult,
                           target_dir: Path) -> dict:
        target_dir.mkdir(parents=True, exist_ok=True)
        images_dir = target_dir / "images"
        images_dir.mkdir(exist_ok=True)
        music_dir = target_dir / "music"
        music_dir.mkdir(exist_ok=True)
        video_dir = target_dir / "video"
        video_dir.mkdir(exist_ok=True)

        result = {
            "images_dir": str(images_dir),
            "images": [],
            "music_path": None,
            "video_path": None,
            "live_photo_videos": [],
        }

        client = await self._get_client()

        # LIVE_PHOTO type: download each pair
        if metadata.live_photo_data:
            live_dir = target_dir / "live_photos"
            live_dir.mkdir(exist_ok=True)
            for i, lp in enumerate(metadata.live_photo_data):
                await progress_emitter.emit_stage(
                    task_id, "downloading_live_photos",
                    i / max(len(metadata.live_photo_data), 1),
                    f"下载实况 {i+1}/{len(metadata.live_photo_data)}",
                    i, len(metadata.live_photo_data)
                )
                if lp.image_url:
                    try:
                        p = await self._download_file(client, lp.image_url, live_dir, f"live_{i:04d}_img")
                        if p:
                            result["images"].append(p)
                    except Exception:
                        pass
                if lp.video_url:
                    try:
                        p = await self._download_file(client, lp.video_url, live_dir, f"live_{i:04d}_vid")
                        if p:
                            result["live_photo_videos"].append(p)
                    except Exception:
                        pass
            # 下载背景音乐
            if metadata.music_url:
                await progress_emitter.emit_stage(task_id, "downloading_music", 0.9, "下载背景音乐", 0, 1)
                try:
                    p = await self._download_file(client, metadata.music_url, music_dir, "music")
                    if p:
                        result["music_path"] = p
                except Exception as e:
                    print(f"音乐下载失败: {e}")

            await progress_emitter.emit_stage(task_id, "downloading_live_photos", 1.0, "下载完成")
            return result

        # VIDEO type: download the video
        if metadata.media_type == MediaType.VIDEO and metadata.music_url:
            await progress_emitter.emit_stage(task_id, "downloading_video", 0, "下载视频中...", 0, 1)
            try:
                p = await self._download_file(client, metadata.music_url, video_dir, "video")
                if p:
                    result["video_path"] = p
            except Exception as e:
                print(f"视频下载失败: {e}")
            for url in metadata.image_urls[:1]:
                try:
                    p = await self._download_file(client, url, images_dir, "cover")
                    if p:
                        result["images"].append(p)
                except Exception:
                    pass
            return result

        # IMAGE_SET: 并行下载所有图片
        img_count = len(metadata.image_urls)
        if img_count > 0:
            await progress_emitter.emit_stage(task_id, "downloading_images",
                0, f"下载 {img_count} 张图片...", 0, img_count)

            async def dl_one(i: int, url: str) -> str | None:
                try:
                    p = await self._download_file(client, url, images_dir, f"image_{i:04d}")
                    return p
                except Exception as e:
                    print(f"图片 {i} 下载失败: {e}")
                    return None

            tasks = [dl_one(i, url) for i, url in enumerate(metadata.image_urls)]
            results = await asyncio.gather(*tasks)
            for p in results:
                if p:
                    result["images"].append(p)

            await progress_emitter.emit_stage(task_id, "downloading_images",
                0.9, f"下载完成 {len(result['images'])}/{img_count} 张", img_count, img_count)

        # 封面（并行）
        cover_task = None
        if metadata.cover_url:
            cover_task = asyncio.create_task(
                self._download_file(client, metadata.cover_url, images_dir, "cover"))

        # 音乐（并行）
        music_task = None
        if metadata.music_url:
            music_task = asyncio.create_task(
                self._download_file(client, metadata.music_url, music_dir, "music"))

        if cover_task:
            p = await cover_task
            if p:
                result["cover_path"] = p
        if music_task:
            p = await music_task
            if p:
                result["music_path"] = p

        # 保存正文文字到 post.txt
        if metadata.text_content:
            txt_path = target_dir / "post.txt"
            try:
                txt_path.write_text(metadata.text_content.strip(), encoding="utf-8")
                result["text_path"] = str(txt_path)
            except Exception as e:
                print(f"文字保存失败: {e}")

        return result

    async def _download_file(self, client: httpx.AsyncClient, url: str,
                             target_dir: Path, prefix: str) -> str | None:
        ext = self._guess_extension(url)
        path = target_dir / f"{prefix}{ext}"
        c = 0
        while path.exists():
            c += 1
            path = target_dir / f"{prefix}_{c}{ext}"
        for a in range(3):
            try:
                async with self.semaphore:
                    resp = await client.get(url)
                    resp.raise_for_status()
                path.write_bytes(resp.content)

                # HEIC/WEBP → JPEG 转换，确保 Windows 可查看
                if ext.lower() in (".heic", ".heif", ".webp"):
                    try:
                        jpg_path = target_dir / f"{path.stem}.jpg"
                        if not jpg_path.exists():
                            from PIL import Image as _PIL
                            if ext.lower() in (".heic", ".heif"):
                                try:
                                    import pillow_heif
                                    pillow_heif.register_heif_opener()
                                except ImportError:
                                    return str(path)
                            img = _PIL.open(path)
                            img.convert("RGB").save(jpg_path, "JPEG", quality=95)
                            # 下载结果返回 JPEG 路径
                            return str(jpg_path)
                    except Exception:
                        pass

                return str(path)
            except Exception as e:
                if a < 2:
                    await asyncio.sleep(1 * (a + 1))
                else:
                    raise e
        return None

    def _guess_extension(self, url: str) -> str:
        # zjcdn.com 域名必定是视频
        if 'zjcdn.com' in url:
            return '.mp4'
        u = url.split("?")[0].split("#")[0].lower()
        for e in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4",
                   ".mov", ".mp3", ".aac", ".m4a", ".heic", ".webm"]:
            if u.endswith(e):
                return e
        return ".jpg"

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


download_manager = DownloadManager()
