"""
Douyin scraper service using Playwright.
Fast path: uses direct API when logged in with session cookies.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import re
import asyncio
import logging
import yaml
import httpx
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from ..models.schemas import ScrapeResult, MediaType, LivePhotoSource, ProfilePost, ProfileResult
from .ttwid import ensure_ttwid

logger = logging.getLogger("scraper")


@dataclass(frozen=True)
class ProfileUrlInfo:
    input_url: str
    resolved_url: str
    sec_uid: str


class DouyinScraper:

    def __init__(self, cookies_path: str | None = None):
        if cookies_path is None:
            try:
                from ..config import settings
                cookies_path = settings.cookies_path
            except Exception:
                cookies_path = "cookies.yaml"
        self.cookies: dict[str, str] = {}
        self._cookies_path = cookies_path
        self._load_cookies(cookies_path)
        self._playwright = None
        self._pw_browser = None
        self._pw_lock = asyncio.Lock()

    async def _get_browser(self):
        async with self._pw_lock:
            if self._pw_browser and hasattr(self._pw_browser, 'contexts'):
                try:
                    await asyncio.wait_for(self._pw_browser.contexts, timeout=0.5)
                    return self._pw_browser
                except Exception:
                    pass
            return await self._launch_new_browser()

    async def _reset_browser(self):
        """关闭当前浏览器进程并启动全新的，用于 WAF 指纹锁定后恢复。"""
        async with self._pw_lock:
            try:
                if self._pw_browser:
                    await self._pw_browser.close()
            except Exception:
                pass
            self._pw_browser = None
            print("[PW] 浏览器已重置（WAF 指纹隔离）")
            return await self._launch_new_browser()

    async def _launch_new_browser(self):
        if self._playwright is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
        launch_args = [
            "--headless=new",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-dev-shm-usage",
            "--no-zygote",
            "--disable-gpu",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-component-update",
            "--window-position=-32000,-32000",
            "--window-size=1,1",
        ]
        for channel in ["chrome", "msedge"]:
            try:
                self._pw_browser = await self._playwright.chromium.launch(
                    channel=channel, headless=True, args=launch_args)
                return self._pw_browser
            except Exception:
                continue
        try:
            from setup_check import get_chromium_path
            exe = get_chromium_path()
            if exe:
                self._pw_browser = await self._playwright.chromium.launch(
                    executable_path=exe, headless=True, args=launch_args)
            else:
                self._pw_browser = await self._playwright.chromium.launch(headless=True, args=launch_args)
        except Exception:
            self._pw_browser = await self._playwright.chromium.launch(headless=True, args=launch_args)
        return self._pw_browser

    async def clear_cache(self):
        """清除浏览器缓存和登录状态。"""
        # 关闭当前浏览器
        if self._pw_browser:
            try:
                await self._pw_browser.close()
            except Exception:
                pass
            self._pw_browser = None
        # 清除 cookies.yaml
        try:
            p = Path(self._cookies_path)
            if p.exists():
                p.unlink()
        except Exception:
            pass
        self.cookies = {}
        print("[PW] 浏览器缓存和Cookie已清除")

    async def close(self):
        if self._pw_browser:
            try:
                await self._pw_browser.close()
            except Exception:
                pass
            self._pw_browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def _close_browser_deadline(self, timeout: float = 30.0):
        await asyncio.sleep(timeout)
        await self.close()

    def _load_cookies(self, path: str):
        p = Path(path)
        if p.exists():
            try:
                data = yaml.safe_load(p.read_text("utf-8"))
                if data:
                    self.cookies = {k: v for k, v in data.items() if v}
            except Exception:
                self.cookies = {}
        self.cookies = ensure_ttwid(self.cookies)

    async def scrape(self, share_url: str) -> ScrapeResult:
        """需登录。先试直调 API，失败后用 Playwright 浏览器调 API（浏览器自动处理签名）。"""
        self._load_cookies(self._cookies_path)
        resolved = self._resolve_url(share_url)
        aweme_id = self._extract_aweme_id(resolved)

        has_session = bool(self.cookies.get("sessionid") or self.cookies.get("sid_tt"))
        if not has_session:
            raise PermissionError("请先登录后再使用。点击右上角「未登录」扫码登录。")
        if not aweme_id:
            raise ValueError("无法识别链接，请确认是抖音分享链接")

        import time as _time_scrape
        _t0 = _time_scrape.time()

        # 路径一：直调 API（最快，需要 a_bogus 签名但有时候能走通）
        result = await self._scrape_via_api(aweme_id)
        if result and result.image_urls:
            result.aweme_id = aweme_id
            print(f"[Scrape] 路径1(API直调) 成功，耗时 {_time_scrape.time()-_t0:.1f}s")
            return result

        # 路径一(b)：f2 库直调（含签名处理，可选依赖）
        result = await self._scrape_via_f2(aweme_id)
        if result and result.image_urls:
            result.aweme_id = aweme_id
            print(f"[Scrape] 路径2(f2库) 成功，耗时 {_time_scrape.time()-_t0:.1f}s")
            return result

        # 路径二：Playwright 浏览器内调 API（浏览器自动处理 a_bogus 签名）
        result = await self._scrape_via_pw_api(aweme_id, resolved)
        if result and result.image_urls:
            result.aweme_id = aweme_id
            print(f"[Scrape] 路径3(PW API) 成功，耗时 {_time_scrape.time()-_t0:.1f}s")
            return result

        # 路径三：Playwright DOM 提取（最终兜底）
        result = await self._scrape_via_playwright(resolved if resolved.startswith("http") else share_url)
        if result and (result.image_urls or result.live_photo_data):
            result.aweme_id = aweme_id or ""
            print(f"[Scrape] 路径4(PW DOM) 成功，耗时 {_time_scrape.time()-_t0:.1f}s")
            return result

        raise RuntimeError("抓取失败，无法获取内容数据。")

    def _resolve_url(self, url: str) -> str:
        try:
            return str(httpx.head(url, follow_redirects=True, timeout=10,
                                  headers={"User-Agent": "Mozilla/5.0"}).url)
        except Exception:
            return url

    def _extract_aweme_id(self, url: str) -> Optional[str]:
        for p in [r"aweme_id=(\d+)", r"/video/(\d+)", r"/note/(\d+)", r"/(\d{17,})"]:
            m = re.search(p, url)
            if m:
                return m.group(1)
        return None

    def _extract_first_url(self, text: str) -> str:
        """Extract the first Douyin URL from pasted share text."""
        text = (text or "").strip()
        if not text:
            return ""
        patterns = [
            r"https?://www\.douyin\.com/user/[^\s]+",
            r"https?://v\.douyin\.com/[^\s]+",
            r"https?://www\.douyin\.com/(?:note|video|share)/[^\s]+",
            r"https?://www\.iesdouyin\.com/[^\s]+",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(0).rstrip("，。；;、)")
        return text

    def _extract_profile_sec_uid(self, profile_text: str) -> ProfileUrlInfo:
        """Resolve a profile/share text to sec_uid, rejecting single-aweme links."""
        input_url = self._extract_first_url(profile_text)
        if not input_url:
            raise ValueError("请输入主页链接")

        if re.search(r"/(?:video|note|share)/\d+", input_url):
            raise ValueError("这是作品链接，请切换到「单个链接抓取」")

        resolved = self._resolve_url(input_url)
        if re.search(r"/(?:video|note|share)/\d+", resolved):
            raise ValueError("这是作品链接，请切换到「单个链接抓取」")

        for candidate in (resolved, input_url):
            m = re.search(r"[?&]sec_uid=([^&#]+)", candidate)
            if m:
                return ProfileUrlInfo(input_url=input_url, resolved_url=resolved, sec_uid=m.group(1))
            m = re.search(r"/user/([^/?#]+)", candidate)
            if m:
                return ProfileUrlInfo(input_url=input_url, resolved_url=resolved, sec_uid=m.group(1))

        raise ValueError("无法从链接中提取用户ID，请确认是主页链接或主页分享文本")

    def _build_profile_api_request(
        self,
        endpoint: str,
        sec_uid: str,
        *,
        max_cursor: int | None = None,
        count: int | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Build Douyin profile API URL and headers with browser context params."""
        cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items() if v)
        params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "pc_client_type": "1",
            "publish_video_strategy_type": "2",
            "pc_libra_divert": "Windows",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "130.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "130.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "12",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "100",
            "sec_user_id": sec_uid,
        }
        if self.cookies.get("msToken"):
            params["msToken"] = self.cookies["msToken"]
        if max_cursor is not None:
            params["max_cursor"] = str(max_cursor)
        if count is not None:
            params["count"] = str(count)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cookie": cookie_str,
        }
        return f"{endpoint}?{urlencode(params)}", headers

    def _parse_detail_to_result(self, detail: dict, page_url: str = "") -> Optional[ScrapeResult]:
        if not detail:
            return None
        title = detail.get("desc", "") or detail.get("title", "") or ""
        author = ""
        if isinstance(detail.get("author"), dict):
            author = detail["author"].get("nickname", "")
        elif isinstance(detail.get("user"), dict):
            author = detail["user"].get("nickname", "")
        if isinstance(detail.get("owner"), dict):
            author = detail["owner"].get("nickname", "") or author
        create_time = detail.get("create_time", 0) or 0
        is_video = bool(detail.get("video")) and not detail.get("image_post_info")
        is_video = is_video or "/video/" in page_url
        music_url = ""
        music_title = ""
        music_data = detail.get("music", {})
        if isinstance(music_data, dict):
            pu = music_data.get("play_url", {})
            if isinstance(pu, dict):
                ul = pu.get("url_list", [])
                if ul and ul[0]:
                    music_url = ul[0]
                    music_title = music_data.get("title", "") or ""
        if is_video:
            video_data = detail.get("video", {})
            if isinstance(video_data, dict):
                play_addr = video_data.get("play_addr", {})
                vlist = play_addr.get("url_list", [])
                cover_list = video_data.get("cover", {}).get("url_list", [])
                cover = cover_list[0] if cover_list else ""
                video_url = vlist[0] if vlist else ""
                return ScrapeResult(title=title, author=author, media_type=MediaType.VIDEO,
                                    image_urls=[cover] if cover else [],
                                    music_url=video_url or music_url or None, music_title=music_title, create_time=create_time)
            return ScrapeResult(title=title, author=author, media_type=MediaType.VIDEO, music_url=music_url or None, create_time=create_time)
        img_sources = []
        if detail.get("image_post_info"):
            img_sources = detail["image_post_info"].get("images", [])
        elif detail.get("images"):
            img_sources = detail["images"]
        elif detail.get("note_images"):
            img_sources = detail["note_images"]
        if not img_sources:
            return None
        seen_urls = set()
        live_data = []
        for img in img_sources:
            if not isinstance(img, dict):
                continue
            ul = img.get("url_list", [])
            if not (ul and ul[0]):
                continue
            img_url = ul[0]
            if img_url in seen_urls:
                continue
            seen_urls.add(img_url)
            video_url = ""
            video_obj = img.get("video")
            if isinstance(video_obj, dict):
                play_addr = video_obj.get("play_addr", {})
                vlist = play_addr.get("url_list", [])
                if vlist and vlist[0]:
                    video_url = vlist[0]
            elif isinstance(img.get("video_url"), str):
                video_url = img["video_url"]
            live_data.append(LivePhotoSource(image_url=img_url, video_url=video_url))
        if not live_data:
            return None
        images = [lp.image_url for lp in live_data]
        has_any_video = any(lp.video_url for lp in live_data)
        all_have_video = all(lp.video_url for lp in live_data) if live_data else False
        if has_any_video and not all_have_video:
            return ScrapeResult(title=title, author=author, media_type=MediaType.COMPREHENSIVE,
                                image_urls=images, live_photo_data=live_data,
                                music_url=music_url or None, music_title=music_title, create_time=create_time)
        if has_any_video:
            return ScrapeResult(title=title, author=author, media_type=MediaType.LIVE_PHOTO,
                                image_urls=images, live_photo_data=live_data,
                                music_url=music_url or None, music_title=music_title, create_time=create_time)
        return ScrapeResult(title=title, author=author, media_type=MediaType.IMAGE_SET,
                            image_urls=images, music_url=music_url or None, music_title=music_title, create_time=create_time)

    async def _scrape_via_api(self, aweme_id: str) -> Optional[ScrapeResult]:
        """直调抖音 API（需要 a_bogus 签名，成功率低，设计中快速失败让 f2 接手）"""
        cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items() if v)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        headers = {"User-Agent": ua, "Referer": "https://www.douyin.com/", "Cookie": cookie_str}
        mobile_headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                          "Referer": "https://www.douyin.com/", "Cookie": cookie_str}

        # 构建所有端点
        all_endpoints = [
            (f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}", headers),
            (f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}&version_code=180800", headers),
            (f"https://www.douyin.com/aweme/v1/web/note/detail/?note_id={aweme_id}", headers),
            (f"https://www.douyin.com/aweme/v1/web/note/detail/?note_id={aweme_id}&version_code=180800", headers),
            (f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}", mobile_headers),
            (f"https://www.douyin.com/aweme/v1/web/note/detail/?note_id={aweme_id}", mobile_headers),
        ]

        # 并行发起，超时 4s，快速失败
        async with httpx.AsyncClient(follow_redirects=True, timeout=4) as c:
            async def try_one(url: str, hdrs: dict):
                try:
                    resp = await c.get(url, headers=hdrs)
                    if resp.status_code != 200:
                        return None
                    data = resp.json()
                    for key in ("aweme_detail", "note_detail"):
                        detail = data.get(key)
                        if detail:
                            result = self._parse_detail_to_result(detail)
                            if result and result.image_urls:
                                return result
                except Exception:
                    pass
                return None

            tasks = [try_one(url, hdrs) for url, hdrs in all_endpoints]
            for coro in asyncio.as_completed(tasks, timeout=4):
                try:
                    r = await coro
                    if r:
                        return r
                except (TimeoutError, asyncio.TimeoutError):
                    continue
                except Exception:
                    continue

        # 兜底：SSR HTML 提取（快速尝试 3s）
        try:
            url = f"https://www.douyin.com/note/{aweme_id}"
            async with httpx.AsyncClient(follow_redirects=True, timeout=3) as c:
                resp = await c.get(url, headers=headers)
                if resp.status_code == 200:
                    html = resp.text
                    for marker in ['id="RENDER_DATA"', 'id="__NEXT_DATA__"']:
                        idx = html.find(marker)
                        if idx > 0:
                            start = html.find('>', idx) + 1
                            end = html.find('</', start)
                            if end > start:
                                raw = html[start:end].strip()
                                if marker == 'id="RENDER_DATA"':
                                    import urllib.parse
                                    try:
                                        raw = urllib.parse.unquote(raw)
                                    except Exception:
                                        pass
                                try:
                                    data = json.loads(raw)
                                    detail = (data.get("aweme_detail") or data.get("note_detail")
                                              or data.get("detail") or {})
                                    result = self._parse_detail_to_result(detail, page_url=url)
                                    if result and result.image_urls:
                                        return result
                                except Exception:
                                    pass
        except Exception:
            pass

        return None

    ENHANCED_STEALTH = """
        // ── 基础反检测（WAF JS 挑战） ──
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
        // chrome.runtime 对象（部分 WAF 检测 chrome.app 是否存在）
        window.chrome = { runtime: {} };
        // WebGL 指纹固定（避免 WAF 通过 WebGL 检测 headless）
        const __gl = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(p) {
            if (p === 37445) return 'Intel Inc.';
            if (p === 37446) return 'Intel Iris OpenGL Engine';
            return __gl.call(this, p);
        };
        // 固定 hardwareConcurrency（避免被检测到 navigator 异常）
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    """

    STEALTH_SCRIPT = ENHANCED_STEALTH

    async def _scrape_via_pw_api(self, aweme_id: str, page_url: str) -> Optional[ScrapeResult]:
        """用 Playwright 渲染页面后从 DOM 提取内容。

        抖音 SPA 已不再使用旧版 /aweme/v1/web/note/detail/ API，改为 Webpack 内联数据。
        WAF 挑战有概率性，策略：
        - 两步导航：先访问首页让 WAF 下发 Cookie，再访问目标页面
        - 智能轮询：每 2s 检查内容是否加载，不等固定时间
        - 最多 3 次重试 + 新上下文
        """
        browser = await self._get_browser()

        for attempt in range(3):
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            try:
                # 增强反检测
                await ctx.add_init_script(DouyinScraper.ENHANCED_STEALTH)
                pw_cookies = [
                    {"name": k, "value": v, "domain": ".douyin.com", "path": "/"}
                    for k, v in self.cookies.items() if v
                ]
                if pw_cookies:
                    await ctx.add_cookies(pw_cookies)

                page = await ctx.new_page()
                nav_url = (page_url if page_url.startswith("http")
                           else f"https://www.douyin.com/note/{aweme_id}")

                # === 两步导航 ===
                # 第一步：访问首页触发 WAF 挑战，等待挑战完成（URL 回到 douyin.com）
                try:
                    await page.goto("https://www.douyin.com/",
                                    wait_until="domcontentloaded", timeout=15000)
                    # 智能等待：每隔 1s 检查 URL 是否从 mon.zijieapi 回到 douyin
                    for _ in range(15):
                        await asyncio.sleep(1)
                        cur = page.url
                        if 'douyin.com' in cur and 'mon.zijie' not in cur:
                            break
                except Exception:
                    pass  # 首页加载失败不中断

                # 第二步：导航到目标笔记页面
                try:
                    await page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    if attempt < 2:
                        logger.error(f"[PW-API] 第{attempt+1}次导航失败，重试...")
                        continue
                    return None

                # 智能轮询：每 2s 检测内容图片是否出现（不等固定时间）
                content_loaded = False
                for _ in range(10):  # 最多等 20s
                    await asyncio.sleep(2)
                    status = await page.evaluate("""() => {
                        const imgs = document.querySelectorAll('img');
                        if (imgs.length === 0) return 'no_images';
                        for (const img of imgs) {
                            const s = img.src || img.getAttribute('data-src') || '';
                            if (s.includes('douyinpic.com') || s.includes('tos-cn-')) return 'content_found';
                        }
                        return 'no_content';
                    }""")
                    if status == 'content_found':
                        content_loaded = True
                        break
                    elif status == 'no_images' and _ >= 2:
                        # 连续 3 个周期（~6s）无任何图片 → 被 WAF 拦了
                        break

                if not content_loaded:
                    if attempt < 2:
                        logger.error(f"[PW-API] 第{attempt+1}次无内容(WAF/超时)，重试...")
                        await asyncio.sleep(2)
                        continue
                    return None

                # 从 DOM 提取内容（主要路径）
                result = await self._extract_dom_to_result(page, nav_url)
                if result and result.image_urls:
                    return result

                # 兜底：旧版内嵌数据提取
                result = await self._extract_from_page_data(page, "/video/" in nav_url)
                if result and result.image_urls:
                    return result

                break  # 有图片但提取失败 → 不再重试
            except Exception as e:
                if attempt < 2:
                    logger.error(f"[PW-API] 第{attempt+1}次异常:{e}，重试...")
                    continue
                logger.error(f"[PW-API] 失败: {e}")
            finally:
                try:
                    await ctx.close()
                except Exception:
                    pass
        return None

    async def _extract_dom_to_result(self, page, page_url: str) -> Optional[ScrapeResult]:
        """从已渲染的 DOM 中提取图片和元数据。"""
        try:
            # 首次提取：收集所有候选图片（含尺寸信息用于自适应过滤）
            data = await page.evaluate("""() => {
                const seen = new Set();
                const items = [];
                const vpW = window.innerWidth, vpH = window.innerHeight;
                const colLeft = vpW * 0.2, colRight = vpW * 0.55;
                document.querySelectorAll('img').forEach(img => {
                    let s = img.src || img.getAttribute('data-src') || '';
                    if (!s) { const bg = window.getComputedStyle(img).backgroundImage;
                        if (bg && bg !== 'none') { const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/); if (m) s = m[1]; } }
                    if (!s || !(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                    if (/emoji|avatar|emblem|douyinDefault|get_app|download|logo|sticker|expression|aweme\\/cover/.test(s)) return;
                    const nw = img.naturalWidth;
                    if (nw > 0 && nw < 80) return;
                    const base = s.split('?')[0].split('~tplv')[0];
                    if (seen.has(base)) return;
                    seen.add(base);
                    const rect = img.getBoundingClientRect();
                    const cx = rect.left + rect.width / 2;
                    const inCenter = cx >= colLeft && cx <= colRight;
                    items.push({
                        url: s, nw: nw, base: base,
                        inViewport: rect.top >= 0 && rect.top < vpH && rect.width > 100,
                        inCenter: inCenter, top: rect.top,
                    });
                });
                return items;
            }""")
            if not data or len(data) == 0:
                return None

            # 自适应过滤：计算尺寸中位数，去掉明显偏小的
            all_nw = sorted([x["nw"] for x in data if x["nw"] > 0])
            median_nw = all_nw[len(all_nw) // 2] if all_nw else 800
            threshold = max(400, median_nw * 0.4)

            # 中心区域优先，其次按尺寸过滤
            center = [x for x in data if x.get("inCenter") and x["nw"] >= threshold]
            other = [x for x in data if not x.get("inCenter") and x["nw"] >= threshold]

            # 如果中心区域有足够的图，只用中心区域的
            source = center if len(center) >= max(2, len(data) * 0.3) else (center + other)

            # 去重、排序
            seen_base = set()
            deduped = []
            for x in source:
                b = x["base"]
                if b not in seen_base:
                    seen_base.add(b)
                    deduped.append(x["url"])

            all_imgs = deduped[:50]
            # 从页面标题提取
            try:
                page_title = await page.evaluate("document.title || ''")
                title = re.sub(r'[#].*', '', (page_title or "")).strip()
            except Exception:
                title = ""

            # 等待一小段时间让懒加载图片加载，再补抓一次
            await asyncio.sleep(1.5)
            more_imgs = await page.evaluate("""() => {
                const seen = new Set();
                const items = [];
                const vpH = window.innerHeight, vpW = window.innerWidth;
                const colLeft = vpW * 0.2, colRight = vpW * 0.55;
                document.querySelectorAll('img').forEach(img => {
                    let s = img.src || img.getAttribute('data-src') || '';
                    if (!s) { const bg = window.getComputedStyle(img).backgroundImage;
                        if (bg && bg !== 'none') { const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/); if (m) s = m[1]; } }
                    if (!s || !(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                    if (/emoji|avatar|emblem|douyinDefault|get_app|download|logo|sticker|expression|aweme\\/cover/.test(s)) return;
                    const nw = img.naturalWidth;
                    if (nw > 0 && nw < 80) return;
                    const rect = img.getBoundingClientRect();
                    if (rect.top > vpH * 0.7) return;
                    const cx = rect.left + rect.width / 2;
                    if (cx < colLeft || cx > colRight) return;
                    const base = s.split('?')[0].split('~tplv')[0];
                    if (seen.has(base)) return;
                    seen.add(base);
                    items.push({url: s, nw: nw});
                });
                // 自适应过滤：只保留尺寸 >= 中位数*0.4 的
                const sizes = items.map(x => x.nw).filter(x => x > 0).sort((a,b) => a-b);
                const med = sizes.length > 0 ? sizes[Math.floor(sizes.length/2)] : 800;
                const thr = Math.max(400, med * 0.4);
                return items.filter(x => x.nw >= thr).map(x => x.url);
            }""")
            # 去重合并
            existing = set(img.split('?')[0].split('~tplv')[0] for img in all_imgs)
            for u in more_imgs:
                base = u.split('?')[0].split('~tplv')[0]
                if base not in existing and len(all_imgs) < 50:
                    existing.add(base)
                    all_imgs.append(u)

            title = re.sub(r'[#].*', '', (data.get("title") or "")).strip()

            # 作者提取：多级选择器兜底
            meta = await page.evaluate("""() => {
                const selectors = [
                    '[class*="nickname"]',
                    '[class*="author-name"]',
                    '[class*="user-name"]',
                    '[class*="UserHeader"]',
                    '[class*="author"]',
                    'a[href*="user"]',
                    '[class*="AvatarAccount"]',
                    'meta[name="author"]',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const text = el.textContent ? el.textContent.trim() : (el.content || '');
                        if (text && text.length > 0 && text.length < 50) return {author: text};
                    }
                }
                // 兜底：搜索含 @ 的文本节点
                const walker = document.createTreeWalker(document.body, 4);
                while (walker.nextNode()) {
                    const t = walker.currentNode.textContent.trim();
                    if (t.startsWith('@') && t.length > 1 && t.length < 50) return {author: t.replace(/^@/, '')};
                }
                return {author: ''};
            }""")

            is_video = "/video/" in page_url
            if is_video:
                video_src = await page.evaluate("""() => {
                    for (const v of document.querySelectorAll('video')) {
                        let src = v.currentSrc || v.src || '';
                        if (!src) { const s = v.querySelector('source'); if (s) src = s.src; }
                        if (src) return src;
                    }
                    return '';
                }""")
                return ScrapeResult(title=title, author=meta.get("author", ""),
                                    media_type=MediaType.VIDEO,
                                    image_urls=all_imgs[:1],
                                    music_url=video_src or None)

            return ScrapeResult(title=title, author=meta.get("author", ""),
                                media_type=MediaType.IMAGE_SET,
                                image_urls=all_imgs)
        except Exception as e:
            logger.error(f"[DOM提取] 失败: {e}")
            return None

    async def _scrape_via_playwright(self, url: str) -> Optional[ScrapeResult]:
        try:
            import playwright
        except ImportError:
            return None
        try:
            browser = await self._get_browser()
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            await ctx.add_init_script(DouyinScraper.ENHANCED_STEALTH)
            try:
                import yaml as _yaml
                ck_path = Path(self._cookies_path)
                if ck_path.exists():
                    ck_data = _yaml.safe_load(ck_path.read_text("utf-8")) or {}
                    playwright_cookies = []
                    for name, value in ck_data.items():
                        if value:
                            playwright_cookies.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})
                    if playwright_cookies:
                        await ctx.add_cookies(playwright_cookies)
            except Exception:
                pass
            page = await ctx.new_page()

            # 两步导航：先刷首页让 WAF 下发挑战 Cookie
            try:
                await page.goto("https://www.douyin.com/",
                                wait_until="domcontentloaded", timeout=15000)
                # 智能等待 WAF 挑战完成（URL 回到 douyin.com）
                for _ in range(15):
                    await asyncio.sleep(1)
                    cur = page.url
                    if 'douyin.com' in cur and 'mon.zijie' not in cur:
                        break
            except Exception:
                pass

            live_videos = []
            music_url_found = None
            async def on_resp(resp):
                nonlocal music_url_found
                u = resp.url
                if 'zjcdn.com' in u and '/video/' in u:
                    live_videos.append(u)
                if not music_url_found and ('ies-music' in u or '/music/' in u):
                    if u.endswith('.mp3') or '.mp3?' in u or u.endswith('.mp4') or '.mp4?' in u:
                        music_url_found = u
            page.on("response", on_resp)

            xhr_detail = asyncio.get_running_loop().create_future()
            async def on_xhr(resp):
                if xhr_detail.done():
                    return
                u = resp.url
                if '/aweme/v1/web/aweme/detail/' in u or '/aweme/v1/web/note/detail/' in u:
                    try:
                        data = await resp.json()
                        detail = data.get('aweme_detail') or data.get('note_detail') or {}
                        if detail.get('image_post_info') or detail.get('images') or detail.get('video'):
                            xhr_detail.set_result(data)
                    except:
                        pass
            page.on("response", on_xhr)

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            try:
                raw_data = await asyncio.wait_for(xhr_detail, timeout=5)
                detail = raw_data.get('aweme_detail') or raw_data.get('note_detail') or {}
                result = self._parse_detail_to_result(detail, page_url=page.url)
                if result:
                    if music_url_found and not result.music_url:
                        result.music_url = music_url_found
                    return result
            except (asyncio.TimeoutError, Exception):
                pass

            page_url = page.url
            is_video_page = "/video/" in page_url
            result = await self._extract_from_page_data(page, is_video_page)
            if result:
                if music_url_found and not result.music_url:
                    result.music_url = music_url_found
                return result

            try:
                await page.wait_for_function("() => document.querySelectorAll('img').length > 10", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(0.5)
            result = await self._extract_from_page_data(page, is_video_page)
            if result:
                if music_url_found and not result.music_url:
                    result.music_url = music_url_found
                return result

            if is_video_page:
                result = await self._extract_from_dom(page)
                if result:
                    if music_url_found and not result.music_url:
                        result.music_url = music_url_found
                    return result
                return ScrapeResult(media_type=MediaType.VIDEO, music_url=music_url_found or "")

            result = await self._extract_carousel(page, live_videos)
            if result and len(result.image_urls) > 2:
                if music_url_found and not result.music_url:
                    result.music_url = music_url_found
                return result

            result = await self._extract_via_viewer(page, music_url_found)
            if result:
                return result

            result = await self._extract_from_dom(page)
            if result:
                if music_url_found and not result.music_url:
                    result.music_url = music_url_found
                return result

            if not music_url_found:
                fallback_music = await page.evaluate("""() => {
                    for (const v of document.querySelectorAll('video')) {
                        let src = v.currentSrc || v.src || '';
                        if (!src) { const s = v.querySelector('source'); if (s) src = s.src; }
                        if (src && (src.includes('ies-music') || src.includes('music.douyin') || src.includes('/music/'))) return src;
                    }
                    for (const a of document.querySelectorAll('audio')) {
                        let src = a.currentSrc || a.src || '';
                        if (src) return src;
                    }
                    return '';
                }""")
                if fallback_music:
                    music_url_found = fallback_music
            # 只在有实际内容时返回结果
            return None
        except Exception as e:
            logger.error(f"[Playwright] 失败: {e}")
            return None
        finally:
            try:
                await ctx.close()
            except Exception:
                pass

    async def _extract_from_page_data(self, page, is_video_page=False) -> Optional[ScrapeResult]:
        try:
            data = await page.evaluate("""() => {
                let raw = null;
                const rd = document.getElementById('RENDER_DATA');
                if (rd) { try { raw = JSON.parse(decodeURIComponent(rd.textContent)); } catch(e) {} }
                if (!raw) { const nd = document.getElementById('__NEXT_DATA__'); if (nd) { try { raw = JSON.parse(nd.textContent); } catch(e) {} } }
                if (!raw && window.__INITIAL_STATE__) { raw = window.__INITIAL_STATE__; }
                return raw ? JSON.stringify(raw).slice(0, 200000) : null;
            }""")
            if not data:
                return None
            raw = json.loads(data)
            def deep_get(obj, *keys):
                for k in keys:
                    if isinstance(obj, dict):
                        obj = obj.get(k, {})
                    else:
                        return {}
                return obj if isinstance(obj, dict) else {}
            detail = (deep_get(raw, "aweme_detail") or deep_get(raw, "note_detail") or deep_get(raw, "detail")
                      or deep_get(raw, "data", "aweme_detail") or deep_get(raw, "data", "note_detail")
                      or deep_get(raw, "props", "pageProps", "aweme_detail") or deep_get(raw, "props", "pageProps", "note_detail"))
            if not detail:
                return None
            title = detail.get("desc", "") or detail.get("title", "") or ""
            author = ""
            if isinstance(detail.get("author"), dict):
                author = detail["author"].get("nickname", "")
            elif isinstance(detail.get("user"), dict):
                author = detail["user"].get("nickname", "")
            if isinstance(detail.get("owner"), dict):
                author = detail["owner"].get("nickname", "") or author
            music_url = ""
            music_title = ""
            music_data = detail.get("music", {})
            if isinstance(music_data, dict):
                pu = music_data.get("play_url", {})
                if isinstance(pu, dict):
                    ul = pu.get("url_list", [])
                    uri = pu.get("uri", "")
                    if ul and ul[0]:
                        music_url = ul[0]
                    elif uri:
                        music_url = uri
                    if music_url:
                        music_title = music_data.get("title", "") or ""
            create_time = detail.get("create_time", 0) or 0
            if is_video_page:
                video_data = detail.get("video", {})
                if isinstance(video_data, dict):
                    play_addr = video_data.get("play_addr", {})
                    vlist = play_addr.get("url_list", [])
                    cover_list = video_data.get("cover", {}).get("url_list", [])
                    cover = cover_list[0] if cover_list else ""
                    return ScrapeResult(title=title, author=author, media_type=MediaType.VIDEO,
                                        image_urls=[cover] if cover else [], music_url=music_url or None, music_title=music_title, create_time=create_time)
                return ScrapeResult(title=title, author=author, media_type=MediaType.VIDEO, create_time=create_time)

            img_sources = []
            if detail.get("image_post_info"):
                img_sources = detail["image_post_info"].get("images", [])
            elif detail.get("images"):
                img_sources = detail["images"]
            elif detail.get("note_images"):
                img_sources = detail["note_images"]
            if not img_sources:
                return None
            live_data = []
            for img in img_sources:
                if not isinstance(img, dict):
                    continue
                ul = img.get("url_list", [])
                if not (ul and ul[0]):
                    continue
                img_url = ul[0]
                video_url = ""
                video_obj = img.get("video")
                if isinstance(video_obj, dict):
                    play_addr = video_obj.get("play_addr", {})
                    vlist = play_addr.get("url_list", [])
                    if vlist and vlist[0]:
                        video_url = vlist[0]
                elif isinstance(img.get("video_url"), str):
                    video_url = img["video_url"]
                live_data.append(LivePhotoSource(image_url=img_url, video_url=video_url))
            if not live_data:
                return None
            images = [lp.image_url for lp in live_data]
            has_any_video = any(lp.video_url for lp in live_data)
            all_have_video = all(lp.video_url for lp in live_data) if live_data else False
            if has_any_video and not all_have_video:
                return ScrapeResult(title=title, author=author, media_type=MediaType.COMPREHENSIVE,
                                    image_urls=images, live_photo_data=live_data, music_url=music_url or None, music_title=music_title, create_time=create_time)
            if has_any_video:
                return ScrapeResult(title=title, author=author, media_type=MediaType.LIVE_PHOTO,
                                    image_urls=images, live_photo_data=live_data, music_url=music_url or None, music_title=music_title, create_time=create_time)
            return ScrapeResult(title=title, author=author, media_type=MediaType.IMAGE_SET,
                                image_urls=images, music_url=music_url or None, music_title=music_title, create_time=create_time)
        except Exception:
            return None

    async def _extract_carousel(self, page, live_videos: list) -> Optional[ScrapeResult]:
        try:
            try:
                await page.wait_for_function("() => document.querySelectorAll('img').length > 20", timeout=10000)
            except Exception:
                pass
            total = await page.evaluate("""() => {
                const swiperSlide = document.querySelector('[class*=\"SwiperSlide\"], [class*=\"swiperSlide\"]');
                if (swiperSlide) {
                    const swiper = swiperSlide.closest('[class*=\"Swiper\"], [class*=\"swiper\"]') || swiperSlide.parentElement;
                    if (swiper) {
                        const slides = swiper.querySelectorAll('[class*=\"Slide\"], [class*=\"slide\"]');
                        if (slides.length > 0) return slides.length;
                        const found = new Set();
                        swiper.querySelectorAll('img').forEach(img => {
                            const s = img.src || img.getAttribute('data-src') || '';
                            if (!(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                            const base = s.split('?')[0].split('~tplv')[0];
                            found.add(base);
                        });
                        if (found.size > 0) return found.size;
                    }
                }
                const found = new Set();
                const vpW = window.innerWidth, vpH = window.innerHeight;
                const colLeft = vpW * 0.2, colRight = vpW * 0.55;
                document.querySelectorAll('img').forEach(img => {
                    const s = img.src || img.getAttribute('data-src') || '';
                    if (!(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                    if (/emoji|avatar|emblem|douyinDefault|get_app|download|logo|aweme\\/cover/.test(s)) return;
                    const nw = img.naturalWidth;
                    if (nw < 400) return;
                    const rect = img.getBoundingClientRect();
                    if (rect.top === 0 && rect.left === 0 && rect.width === 0) return;
                    const centerX = rect.left + rect.width / 2;
                    if (centerX < colLeft || centerX > colRight) return;
                    if (rect.top > vpH * 0.6) return;
                    const base = s.replace(/^https?:/, '').split('?')[0].split('~tplv')[0];
                    found.add(base);
                });
                return found.size;
            }""")
            if not total or total <= 0:
                return None
            max_content = min(total, 30)

            meta = await page.evaluate("""()=>{
                const d=document.querySelector('meta[name="description"]');
                let nick = '';
                const el = document.querySelector('[class*="nickname"], [class*="author-name"], [class*="user-name"]');
                if (el) nick = el.textContent.trim();
                if (!nick) { const a = document.querySelector('a[href*="user"]'); if (a) nick = a.textContent.trim(); }
                return{title:document.title||'',desc:d?d.content:'', author:nick};
            }""")
            title = re.sub(r'[#].*', '', meta.get("title", "")).strip()
            author = meta.get("author", "") or ""

            all_images = await page.evaluate("""() => {
                const seen = new Set(); const results = [];
                const getUrl = (el) => {
                    let s = el.src || el.getAttribute('data-src') || '';
                    if (!s) { const bg = window.getComputedStyle(el).backgroundImage; if (bg && bg !== 'none') { const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/); if (m) s = m[1]; } }
                    return s;
                };
                const swiperSlide = document.querySelector('[class*=\"SwiperSlide\"], [class*=\"swiperSlide\"]');
                if (swiperSlide) {
                    const swiper = swiperSlide.closest('[class*=\"Swiper\"], [class*=\"swiper\"]') || swiperSlide.parentElement;
                    if (swiper) {
                        swiper.querySelectorAll('img').forEach(img => {
                            const s = getUrl(img);
                            if (!s || !(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                            const base = s.split('?')[0].split('~tplv')[0];
                            if (!seen.has(base)) { seen.add(base); results.push(s); }
                        });
                        if (results.length > 0) return results;
                    }
                }
                const vpW = window.innerWidth, vpH = window.innerHeight;
                const colLeft = vpW * 0.2, colRight = vpW * 0.55;
                document.querySelectorAll('img').forEach(img => {
                    let s = getUrl(img);
                    if (!s || /emoji|avatar|emblem|douyinDefault|get_app|download|logo/.test(s)) return;
                    if (!(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                    const nw2 = img.naturalWidth;
                    if (nw2 < 400) return;
                    const rect = img.getBoundingClientRect();
                    if (rect.top === 0 && rect.left === 0 && rect.width === 0) return;
                    if (rect.top > vpH * 0.6) return;
                    const centerX = rect.left + rect.width / 2;
                    if (centerX < colLeft || centerX > colRight) return;
                    const base = s.split('?')[0].split('~tplv')[0];
                    if (seen.has(base)) return;
                    seen.add(base);
                    results.push(s);
                });
                return results;
            }""")

            seen_base_urls = set()
            for s in all_images:
                seen_base_urls.add(s.split('?')[0].split('~tplv')[0])

            for i in range(max_content):
                await asyncio.sleep(0.1)
                if i < max_content - 1:
                    await page.keyboard.press("ArrowRight")
                    await asyncio.sleep(0.1)
                await asyncio.sleep(0.5)
                if i > 0:
                    new_imgs = await page.evaluate("""() => {
                        const seen = new Set(); const results = [];
                        const swiperSlide = document.querySelector('[class*=\"SwiperSlide\"], [class*=\"swiperSlide\"]');
                        const container = swiperSlide ? (swiperSlide.closest('[class*=\"Swiper\"], [class*=\"swiper\"]') || swiperSlide.parentElement) : null;
                        if (!container) return results;
                        container.querySelectorAll('img').forEach(img => {
                            let s = img.src || img.getAttribute('data-src') || '';
                            if (!s) { const bg = window.getComputedStyle(img).backgroundImage; if (bg && bg !== 'none') { const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/); if (m) s = m[1]; } }
                            if (!s || /emoji|avatar|emblem|douyinDefault|get_app|download|logo/.test(s)) return;
                            if (!(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                            const base = s.split('?')[0].split('~tplv')[0];
                            if (seen.has(base)) return;
                            seen.add(base); results.push(s);
                        });
                        return results;
                    }""")
                    for u in new_imgs:
                        base = u.split('?')[0].split('~tplv')[0]
                        if base not in seen_base_urls:
                            seen_base_urls.add(base)
                            all_images.append(u)

            unique_v = []
            seen_v = set()
            for v in live_videos:
                b = v.split("?")[0]
                if b not in seen_v:
                    seen_v.add(b)
                    unique_v.append(v)

            n = min(len(all_images) if all_images else max_content, max_content)
            pairs = []
            for i in range(n):
                img_url = all_images[i] if i < len(all_images) else ""
                v_url = unique_v[i] if i < len(unique_v) else ""
                pairs.append({"image": img_url, "video": v_url})
            live = [p for p in pairs if p["image"]]
            if not live:
                return None
            has_any_video = any(p.get("video") for p in live)
            all_have_video = all(p.get("video") for p in live) if live else False
            if has_any_video and not all_have_video:
                media_type = MediaType.COMPREHENSIVE
            elif has_any_video:
                media_type = MediaType.LIVE_PHOTO
            else:
                media_type = MediaType.IMAGE_SET
            return ScrapeResult(title=title, media_type=media_type, image_urls=[p["image"] for p in live],
                                live_photo_data=[LivePhotoSource(image_url=p["image"], video_url=p.get("video") or "") for p in live])
        except Exception as e:
            logger.error(f"[轮播提取] 失败: {e}")
            return None

    async def _extract_via_viewer(self, page, music_url_found=None) -> Optional[ScrapeResult]:
        """点击第一张内容图打开全屏 viewer，翻页收集所有懒加载图片。"""
        try:
            has_content = await page.evaluate("""() => {
                const imgs = [...document.querySelectorAll('img')].filter(
                    i => (i.src || '').includes('douyinpic.com') && i.naturalWidth > 400
                );
                for (const img of imgs) {
                    const r = img.getBoundingClientRect();
                    if (r.left > 50 && r.left < 500 && r.top > 0) { img.click(); return true; }
                }
                if (imgs.length > 0) { imgs[0].click(); return true; }
                return false;
            }""")
            if not has_content:
                return None
            await asyncio.sleep(1)

            async def collect_large():
                return await page.evaluate("""() => {
                    const seen = new Set(); const results = [];
                    const vpW = window.innerWidth, vpH = window.innerHeight;
                    const colLeft = vpW * 0.2, colRight = vpW * 0.55;
                    document.querySelectorAll('img').forEach(img => {
                        const s = img.src || img.getAttribute('data-src') || '';
                        if (!s || !(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                        if (/aweme\\/cover/.test(s)) return;
                        if (img.naturalWidth < 1000) return;
                        const rect = img.getBoundingClientRect();
                        const cx = rect.left + rect.width / 2;
                        if (cx < colLeft || cx > colRight) return;
                        const base = s.split('?')[0].split('~tplv')[0];
                        if (seen.has(base)) return;
                        seen.add(base);
                        results.push(s);
                    });
                    return results;
                }""")

            # 首次收集
            all_urls = []
            seen_bases = set()
            init = await collect_large()
            for u in init:
                b = u.split('?')[0].split('~tplv')[0]
                if b not in seen_bases:
                    seen_bases.add(b)
                    all_urls.append(u)

            # 翻页收集（最多 20 次，连续 3 次无新图则退出）
            idle = 0
            for _ in range(20):
                await page.keyboard.press("ArrowRight")
                await asyncio.sleep(0.5)
                new = await collect_large()
                added = 0
                for u in new:
                    b = u.split('?')[0].split('~tplv')[0]
                    if b not in seen_bases:
                        seen_bases.add(b)
                        all_urls.append(u)
                        added += 1
                if added == 0:
                    idle += 1
                    if idle >= 3:
                        break
                else:
                    idle = 0

            if len(all_urls) < 1:
                return None
            return ScrapeResult(media_type=MediaType.IMAGE_SET, image_urls=all_urls, music_url=music_url_found or None)
        except Exception as e:
            logger.error(f"[Viewer] 失败: {e}")
            return None

    async def _extract_from_dom(self, page) -> Optional[ScrapeResult]:
        try:
            pd = await page.evaluate("""() => {
                const getUrl = (el) => {
                    let s = el.src || el.getAttribute('data-src') || '';
                    if (!s || s.startsWith('data:')) { const bg = window.getComputedStyle(el).backgroundImage; if (bg && bg !== 'none') { const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/); if (m) s = m[1]; } }
                    return s;
                };
                const swiper = document.querySelector('[class*=\"SwiperSlide\"], [class*=\"swiperSlide\"]');
                if (swiper) {
                    const parent = swiper.closest('[class*=\"Swiper\"], [class*=\"swiper\"]') || swiper.parentElement;
                    if (parent) {
                        const imgs = []; const seen = new Set();
                        parent.querySelectorAll('img').forEach(img => {
                            let s = getUrl(img);
                            if (!s || seen.has(s)) return;
                            if (!(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                            seen.add(s); imgs.push({src:s, isSwiper: true});
                        });
                        if (imgs.length > 0) {
                            let vs = '';
                            for (const v of document.querySelectorAll('video')) {
                                let src = v.currentSrc || v.src || '';
                                if (src && !src.includes('douyin-pc-web') && !src.includes('uuu_')) { vs = src; break; }
                                for (const s of v.querySelectorAll('source')) { if (s.src && !s.src.includes('douyin-pc-web') && !s.src.includes('uuu_')) { vs = s.src; break; } }
                                if (vs) break;
                            }
                            return JSON.stringify({images:imgs, videoSrc:vs});
                        }
                    }
                }
                const imgs = []; const seen = new Set();
                const vpW = window.innerWidth, vpH = window.innerHeight;
                const colLeft = vpW * 0.2, colRight = vpW * 0.55;
                document.querySelectorAll('img').forEach(img => {
                    let s = getUrl(img);
                    if (!s || seen.has(s) || /emoji|twemoji|get_app|avatar|emblem|douyinDefault|aweme\\/cover/.test(s)) return;
                    if (!(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                    const nw = img.naturalWidth;
                    if (nw < 400) return;
                    const rect = img.getBoundingClientRect();
                    if (rect.top === 0 && rect.left === 0 && rect.width === 0) return;
                    if (rect.top > vpH * 0.6) return;
                    const centerX = rect.left + rect.width / 2;
                    if (centerX < colLeft || centerX > colRight) return;
                    seen.add(s); imgs.push({src:s});
                });
                if (imgs.length === 0) {
                    document.querySelectorAll('img').forEach(img => {
                        let s = getUrl(img);
                        if (!s || seen.has(s)) return;
                        if (!(s.includes('douyinpic.com') || s.includes('tos-cn-'))) return;
                        if (img.naturalWidth > 0 && img.naturalWidth < 400) return;
                        seen.add(s); imgs.push({src:s});
                    });
                }
                let vs = '';
                for (const v of document.querySelectorAll('video')) {
                    let src = v.currentSrc || v.src || '';
                    if (src && !src.includes('douyin-pc-web') && !src.includes('uuu_')) { vs = src; break; }
                    for (const s of v.querySelectorAll('source')) { if (s.src && !s.src.includes('douyin-pc-web') && !s.src.includes('uuu_')) { vs = s.src; break; } }
                    if (vs) break;
                }
                return JSON.stringify({images:imgs, videoSrc:vs});
            }""")
            if not pd:
                return None
            parsed = json.loads(pd)
            all_imgs = parsed.get("images", [])
            if not all_imgs:
                return None
            seen = set()
            dedup = []
            for img in all_imgs:
                base = img["src"].split("?")[0].split("~tplv")[0]
                if base not in seen:
                    seen.add(base)
                    dedup.append(img)
            imgs = [i["src"] for i in dedup[:30]]
            meta = await page.evaluate("""()=>{
                const d=document.querySelector('meta[name="description"]');
                return{title:document.title||'',desc:d?d.content:''};
            }""")
            title = re.sub(r'[#].*', '', meta.get("title", "")).strip()
            is_vid = "/video/" in page.url
            vs = parsed.get("videoSrc", "") or ""
            if is_vid and vs:
                return ScrapeResult(title=title, media_type=MediaType.VIDEO, image_urls=imgs[:1], music_url=vs)
            if imgs and vs and not is_vid:
                return ScrapeResult(title=title, media_type=MediaType.LIVE_PHOTO,
                                    image_urls=imgs, live_photo_data=[LivePhotoSource(image_url=imgs[0], video_url=vs)])
            if imgs:
                return ScrapeResult(title=title, media_type=MediaType.IMAGE_SET, image_urls=imgs)
            return None
        except Exception as e:
            logger.error(f"[DOM提取] 失败: {e}")
            return None

    async def _scrape_via_f2(self, aweme_id: Optional[str]) -> Optional[ScrapeResult]:
        if not aweme_id:
            return None
        try:
            # 抑制 f2 库的无关日志
            import logging
            for lg in ['f2', 'f2.apps.douyin', 'f2.crawlers', 'httpx']:
                logging.getLogger(lg).setLevel(logging.WARNING)
            # 禁用 f2 的 Bark 通知（避免 api.day.app 超时重试卡住 60s+）
            from f2.apps.douyin.handler import DouyinHandler, BarkClientConfManager
            BarkClientConfManager.client_conf["enable_bark"] = False
        except ImportError:
            return None
        try:
            cs = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            h = DouyinHandler(kwargs={"headers": {"User-Agent": "Mozilla/5.0"}, "cookie": cs})
            r = await h.fetch_one_video(aweme_id=aweme_id)
            raw = r if isinstance(r, dict) else r.__dict__
            # f2 返回结构：{_data: {aweme_detail: {...}}}
            detail = raw.get("_data", {}).get("aweme_detail", {})
            if not detail:
                return None

            title = detail.get("desc", "") or detail.get("title", "") or ""
            author = ""
            if isinstance(detail.get("author"), dict):
                author = detail["author"].get("nickname", "")
            elif isinstance(detail.get("user"), dict):
                author = detail["user"].get("nickname", "")
            if isinstance(detail.get("owner"), dict):
                author = detail["owner"].get("nickname", "") or author

            # 提取图片和实况照片数据
            img_sources = []
            if detail.get("image_post_info"):
                img_sources = detail["image_post_info"].get("images", [])
            elif detail.get("images"):
                img_sources = detail["images"]
            elif detail.get("note_images"):
                img_sources = detail["note_images"]

            seen_urls = set()
            live_data = []
            for img in img_sources:
                if not isinstance(img, dict):
                    continue
                ul = img.get("url_list", [])
                if not (ul and ul[0]):
                    continue
                img_url = ul[0]
                if img_url in seen_urls:
                    continue
                seen_urls.add(img_url)
                # 检测实况照片视频
                video_url = ""
                video_obj = img.get("video")
                if isinstance(video_obj, dict):
                    play_addr = video_obj.get("play_addr", {})
                    vlist = play_addr.get("url_list", [])
                    if vlist and vlist[0]:
                        video_url = vlist[0]
                elif isinstance(img.get("video_url"), str):
                    video_url = img["video_url"]
                live_data.append(LivePhotoSource(image_url=img_url, video_url=video_url))

            if not live_data:
                # 兜底：直接搜 dict 里的 url
                for f in ["image_data", "images", "note_images"]:
                    for x in (detail.get(f, []) or []):
                        if isinstance(x, dict):
                            u = x.get("url") or x.get("display_url") or (x.get("url_list") or [None])[0]
                            if u and u.startswith("http") and u not in seen_urls:
                                seen_urls.add(u)
                                live_data.append(LivePhotoSource(image_url=u, video_url=""))

            if not live_data:
                return None

            # 提取音乐信息
            music_url = ""
            music_title = ""
            music_data = detail.get("music", {})
            if isinstance(music_data, dict):
                pu = music_data.get("play_url", {})
                if isinstance(pu, dict):
                    ul = pu.get("url_list", [])
                    uri = pu.get("uri", "")
                    if ul and ul[0]:
                        music_url = ul[0]
                    elif uri:
                        music_url = uri
                    if music_url:
                        music_title = music_data.get("title", "") or ""

            # 正文文字（desc 包含标题+正文+#话题）
            text_content = detail.get("desc", "") or ""

            # 判断媒体类型
            images = [lp.image_url for lp in live_data]
            has_any_video = any(lp.video_url for lp in live_data)
            all_have_video = all(lp.video_url for lp in live_data) if live_data else False
            if has_any_video and not all_have_video:
                media_type = MediaType.COMPREHENSIVE
            elif has_any_video:
                media_type = MediaType.LIVE_PHOTO
            else:
                media_type = MediaType.IMAGE_SET

            return ScrapeResult(
                title=title, author=author, media_type=media_type,
                image_urls=images, live_photo_data=live_data,
                music_url=music_url or None, music_title=music_title,
                text_content=text_content,
            )
        except Exception as e:
            logger.error(f"[f2] 失败: {e}")
        return None

    async def _find_profile_by_author(self, author_name: str) -> str | None:
        """通过作者名搜索主页链接。访问抖音搜索页查找。"""
        browser = await self._get_browser()
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        try:
            await ctx.add_init_script(DouyinScraper.ENHANCED_STEALTH)
            pw_cookies = [
                {"name": k, "value": v, "domain": ".douyin.com", "path": "/"}
                for k, v in self.cookies.items() if v
            ]
            if pw_cookies:
                await ctx.add_cookies(pw_cookies)
            page = await ctx.new_page()
            # 两步导航
            try:
                await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=15000)
                for _ in range(10):
                    await asyncio.sleep(1)
                    if 'douyin.com' in page.url and 'mon.zijie' not in page.url:
                        break
            except Exception:
                pass
            # 搜索作者名
            search_url = f"https://www.douyin.com/search/{author_name}?type=user"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            # 提取第一个用户链接
            profile_url = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/user/"]');
                for (const a of links) {
                    const href = a.href || '';
                    if (href.includes('/user/MS4wLjAB')) return href;
                    if (href.match(/\\/user\\/[^/]+/)) return href;
                }
                return '';
            }""")
            return profile_url or None
        except Exception as e:
            logger.error(f"[Profile] 搜索作者失败: {e}")
            return None
        finally:
            try:
                await ctx.close()
            except Exception:
                pass

    async def _extract_author_profile_url(self, post_url: str) -> str | None:
        """从帖子页面提取作者主页链接。"""
        browser = await self._get_browser()
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        try:
            await ctx.add_init_script(DouyinScraper.ENHANCED_STEALTH)
            pw_cookies = [
                {"name": k, "value": v, "domain": ".douyin.com", "path": "/"}
                for k, v in self.cookies.items() if v
            ]
            if pw_cookies:
                await ctx.add_cookies(pw_cookies)
            page = await ctx.new_page()
            try:
                await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=15000)
                for _ in range(10):
                    await asyncio.sleep(1)
                    if 'douyin.com' in page.url and 'mon.zijie' not in page.url:
                        break
            except Exception:
                pass
            await page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            # 提取作者主页链接
            url = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/user/"]');
                for (const a of links) {
                    const href = a.href || '';
                    if (href.includes('/user/')) return href;
                }
                return '';
            }""")
            return url or None
        except Exception:
            return None
        finally:
            try:
                await ctx.close()
            except Exception:
                pass

    async def scrape_profile(
        self,
        profile_url: str,
        max_posts: int = 30,
        max_cursor: int = 0,
    ) -> ProfileResult:
        """抓取用户主页作品列表。每次只取一页，由用户主动翻到下一页。"""
        self._load_cookies(self._cookies_path)
        parsed = self._extract_profile_sec_uid(profile_url)
        sec_uid = parsed.sec_uid

        user_name = ""
        user_id = sec_uid
        avatar_url = ""
        posts = []

        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            # 2) 获取用户信息
            try:
                profile_url_api, headers = self._build_profile_api_request(
                    "https://www.douyin.com/aweme/v1/web/user/profile/other/",
                    sec_uid,
                )
                profile_resp = await client.get(
                    profile_url_api,
                    headers=headers,
                )
                profile_data = profile_resp.json()
                if not isinstance(profile_data, dict):
                    raise ValueError("用户信息接口返回格式异常")
                user = profile_data.get("user", {})
                user_name = user.get("nickname", "")
                user_id = str(user.get("uid", sec_uid))
                avatar_larger = user.get("avatar_larger", {})
                if isinstance(avatar_larger, dict):
                    url_list = avatar_larger.get("url_list", [])
                    avatar_url = url_list[0] if url_list else ""
                print(f"[Profile] 用户: {user_name} (uid={user_id})")
            except Exception as e:
                print(f"[Profile] 获取用户信息失败: {e}")

            # 3) 分页获取作品列表
            has_more = True
            next_cursor = int(max_cursor or 0)
            seen_ids = set()
            while has_more and len(posts) < max_posts:
                try:
                    post_url_api, headers = self._build_profile_api_request(
                        "https://www.douyin.com/aweme/v1/web/aweme/post/",
                        sec_uid,
                        max_cursor=next_cursor,
                        count=20,
                    )
                    post_resp = await client.get(
                        post_url_api,
                        headers=headers,
                    )
                    post_data = post_resp.json()
                    if not isinstance(post_data, dict):
                        raise ValueError("作品列表接口返回格式异常")
                    if post_data.get("status_code") not in (None, 0):
                        raise ValueError(post_data.get("status_msg") or "作品列表接口返回错误")
                    aweme_list = post_data.get("aweme_list", [])
                    if not aweme_list:
                        break
                    for item in aweme_list:
                        aweme_id = str(item.get("aweme_id", ""))
                        if not aweme_id or aweme_id in seen_ids:
                            continue
                        seen_ids.add(aweme_id)
                        desc = item.get("desc", "") or ""
                        has_video = bool(item.get("video"))
                        has_images = bool(item.get("image_post_info"))
                        media_type = "image" if has_images else "video"
                        create_time = item.get("create_time", 0) or 0
                        cover = ""
                        video_url = ""
                        image_urls = []
                        live_data = []
                        music_url = ""
                        music_title = ""
                        if has_video:
                            video_data = item.get("video", {}) if isinstance(item.get("video"), dict) else {}
                            covers = video_data.get("cover", {}).get("url_list", [])
                            cover = covers[0] if covers else ""
                            play_urls = video_data.get("play_addr", {}).get("url_list", [])
                            video_url = play_urls[0] if play_urls else ""
                        if has_images:
                            imgs = item.get("image_post_info", {}).get("images", [])
                            for img in imgs:
                                if not isinstance(img, dict):
                                    continue
                                ul = img.get("url_list", [])
                                img_url = ul[0] if ul else ""
                                if not img_url:
                                    continue
                                image_urls.append(img_url)
                                lp_video_url = ""
                                lp_video = img.get("video")
                                if isinstance(lp_video, dict):
                                    lp_play = lp_video.get("play_addr", {}).get("url_list", [])
                                    lp_video_url = lp_play[0] if lp_play else ""
                                elif isinstance(img.get("video_url"), str):
                                    lp_video_url = img["video_url"]
                                live_data.append(LivePhotoSource(image_url=img_url, video_url=lp_video_url))
                            if image_urls:
                                cover = image_urls[0]
                        music_data = item.get("music", {})
                        if isinstance(music_data, dict):
                            play_url = music_data.get("play_url", {})
                            if isinstance(play_url, dict):
                                urls = play_url.get("url_list", [])
                                music_url = urls[0] if urls else ""
                            music_title = music_data.get("title", "") or ""
                        post_type = "note" if has_images else "video"
                        posts.append(ProfilePost(
                            aweme_id=aweme_id,
                            desc=desc,
                            cover_url=cover,
                            media_type=media_type,
                            share_url=f"https://www.douyin.com/{post_type}/{aweme_id}",
                            create_time=create_time,
                            image_urls=image_urls or ([cover] if cover else []),
                            video_url=video_url,
                            music_url=music_url,
                            music_title=music_title,
                            live_photo_data=live_data,
                        ))
                        if len(posts) >= max_posts:
                            break
                    has_more = bool(post_data.get("has_more", False))
                    next_cursor = int(post_data.get("max_cursor", 0) or 0)
                except Exception as e:
                    print(f"[Profile] 获取作品列表失败: {e}")
                    break

        print(f"[Profile] 共获取 {len(posts)} 个作品")
        return ProfileResult(
            user_name=user_name,
            user_id=user_id,
            avatar_url=avatar_url,
            posts=posts,
            total=len(posts),
            has_more=has_more,
            next_cursor=next_cursor,
            page_size=max_posts,
        )


# Global scraper instance (shared across routers)
scraper = DouyinScraper()
