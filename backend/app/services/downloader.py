from __future__ import annotations
import asyncio
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
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
            "text_path": None,
        }

        client = await self._get_client()
        live_photo_pairs = [
            lp for lp in (metadata.live_photo_data or [])
            if (lp.image_url or "").strip() and (lp.video_url or "").strip()
        ]
        live_image_only_urls = [
            lp.image_url for lp in (metadata.live_photo_data or [])
            if (lp.image_url or "").strip() and not (lp.video_url or "").strip()
        ]
        image_urls = list(metadata.image_urls or [])
        seen_image_urls = set(image_urls)
        for url in live_image_only_urls:
            if url not in seen_image_urls:
                image_urls.append(url)
                seen_image_urls.add(url)

        # LIVE_PHOTO type: only image+video pairs are treated as real live photos.
        if live_photo_pairs:
            live_dir = target_dir / "live_photos"
            live_dir.mkdir(exist_ok=True)
            for i, lp in enumerate(live_photo_pairs):
                await progress_emitter.emit_stage(
                    task_id, "downloading_live_photos",
                    i / max(len(live_photo_pairs), 1),
                    f"下载实况 {i+1}/{len(live_photo_pairs)}",
                    i, len(live_photo_pairs)
                )
                img_dl = vid_dl = None
                if lp.image_url:
                    try:
                        img_dl = await self._download_file(client, lp.image_url, live_dir, f"live_{i:04d}_img")
                        if img_dl:
                            result["images"].append(img_dl)
                    except Exception:
                        pass
                if lp.video_url:
                    try:
                        vid_dl = await self._download_file(client, lp.video_url, live_dir, f"live_{i:04d}_vid")
                        if vid_dl:
                            result["live_photo_videos"].append(vid_dl)
                    except Exception:
                        pass
                # 合成实况照片：视频 + 静态图 → 一个 mp4
                synth_path = live_dir / f"live_{i:04d}.mp4"
                if img_dl and vid_dl and not synth_path.exists():
                    try:
                        await self._synthesize_live_photo(img_dl, vid_dl, str(synth_path))
                        result.setdefault("live_photo_synths", []).append(str(synth_path))
                    except Exception as e:
                        print(f"实况合成失败 live_{i:04d}: {e}")
            if image_urls:
                await self._download_image_urls(task_id, client, image_urls, images_dir, result)

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
            self._save_post_text(metadata, target_dir, result)
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
            self._save_post_text(metadata, target_dir, result)
            return result

        # IMAGE_SET: 并行下载所有图片
        if image_urls:
            await self._download_image_urls(task_id, client, image_urls, images_dir, result)

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

        self._save_post_text(metadata, target_dir, result)

        return result

    async def _download_image_urls(
        self,
        task_id: str,
        client: httpx.AsyncClient,
        image_urls: list[str],
        images_dir: Path,
        result: dict,
    ) -> None:
        img_count = len(image_urls)
        await progress_emitter.emit_stage(
            task_id, "downloading_images",
            0, f"下载 {img_count} 张图片...", 0, img_count
        )

        async def dl_one(i: int, url: str) -> str | None:
            try:
                return await self._download_file(client, url, images_dir, f"image_{i:04d}")
            except Exception as e:
                print(f"图片 {i} 下载失败: {e}")
                return None

        tasks = [dl_one(i, url) for i, url in enumerate(image_urls)]
        results = await asyncio.gather(*tasks)
        for p in results:
            if p and p not in result["images"]:
                result["images"].append(p)

        await progress_emitter.emit_stage(
            task_id, "downloading_images",
            0.9, f"下载完成 {len(result['images'])}/{img_count} 张", img_count, img_count
        )

    def _save_post_text(self, metadata: ScrapeResult, target_dir: Path, result: dict) -> None:
        text = (metadata.text_content or metadata.title or "").strip()
        if not text:
            return
        txt_path = target_dir / "post.txt"
        try:
            txt_path.write_text(text, encoding="utf-8")
            result["text_path"] = str(txt_path)
        except Exception as e:
            print(f"文字保存失败: {e}")

    async def _download_file(self, client: httpx.AsyncClient, url: str,
                             target_dir: Path, prefix: str) -> str | None:
        ext = self._guess_extension(url)
        path = self._unique_path(target_dir, prefix, ext)
        for a in range(3):
            try:
                async with self.semaphore:
                    resp = await client.get(url)
                    resp.raise_for_status()
                detected_ext = self._guess_extension(
                    url,
                    content_type=resp.headers.get("content-type", ""),
                    content=resp.content,
                )
                if detected_ext != ext:
                    ext = detected_ext
                    path = self._unique_path(target_dir, prefix, ext)
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
                            try:
                                path.unlink()
                            except OSError:
                                pass
                            # 下载结果返回 JPEG 路径，不把转换前文件暴露成第二份素材。
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

    def _unique_path(self, target_dir: Path, prefix: str, ext: str) -> Path:
        path = target_dir / f"{prefix}{ext}"
        c = 0
        while path.exists():
            c += 1
            path = target_dir / f"{prefix}_{c}{ext}"
        return path

    async def _synthesize_live_photo(self, image_path: str, video_path: str, output_path: str) -> None:
        """用 FFmpeg 合成实况照片：视频 + 静态图定格 → 一个 mp4."""
        import subprocess as sp
        import sys
        ffmpeg = settings.ffmpeg_path
        kwargs = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "timeout": 60}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(sp, "CREATE_NO_WINDOW", 0)

        # 视频在前，图片定格 1.5 秒在后。两路输入先统一画布、帧率、时基和像素格式，
        # 避免 FFmpeg concat 因宽高、SAR 或 timebase 不一致直接失败。
        video_filter = (
            "settb=AVTB,setpts=PTS-STARTPTS,fps=30,"
            "scale=1080:1920:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2:flags=lanczos,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
        )
        image_filter = (
            "settb=AVTB,setpts=PTS-STARTPTS,trim=duration=1.5,fps=30,"
            "scale=1080:1920:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2:flags=lanczos,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
        )
        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-loop", "1", "-t", "1.5", "-i", image_path,
            "-filter_complex",
            f"[0:v]{video_filter}[v0];"
            f"[1:v]{image_filter}[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[v]",
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: sp.run(cmd, **kwargs)
        )
        if result.returncode != 0:
            raise RuntimeError(self._compact_ffmpeg_error(result.stderr))

    @staticmethod
    def _compact_ffmpeg_error(stderr: str | None) -> str:
        if not stderr:
            return "unknown"
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        useful = [
            line for line in lines
            if (
                "error" in line.lower()
                or "failed" in line.lower()
                or "invalid" in line.lower()
                or "do not match" in line.lower()
                or "conversion failed" in line.lower()
            )
        ]
        return "; ".join((useful or lines)[-6:])

    def _guess_extension(
        self,
        url: str,
        content_type: str = "",
        content: bytes | None = None,
    ) -> str:
        content_type_l = (content_type or "").split(";")[0].strip().lower()
        if content_type_l in ("video/mp4", "application/mp4", "video/x-m4v"):
            return ".mp4"
        if content_type_l in ("audio/mpeg", "audio/mp3"):
            return ".mp3"
        if content_type_l in ("image/jpeg", "image/jpg"):
            return ".jpg"
        if content_type_l == "image/webp":
            return ".webp"
        if content_type_l == "image/png":
            return ".png"

        if content:
            head = content[:32]
            if len(head) >= 12 and head[4:8] == b"ftyp":
                return ".mp4"
            if head.startswith(b"\xff\xd8\xff"):
                return ".jpg"
            if head.startswith(b"RIFF") and b"WEBP" in head[:16]:
                return ".webp"
            if head.startswith(b"ID3"):
                return ".mp3"

        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = unquote(parsed.path).lower()
        query = parsed.query.lower()
        query_values = " ".join(
            v.lower()
            for values in parse_qs(parsed.query).values()
            for v in values
            if isinstance(v, str)
        )
        hints = f"{query} {query_values}"

        if "video_mp4" in hints or "video/mp4" in hints:
            return ".mp4"
        if "audio_mpeg" in hints or "audio_mp3" in hints:
            return ".mp3"

        # Douyin video CDN URLs often omit a .mp4 suffix and only expose
        # video-ness through host/path/query hints.
        if "zjcdn.com" in host or ("douyinvod.com" in host and "/video/" in path):
            return '.mp4'

        u = path
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
