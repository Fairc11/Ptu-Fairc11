"""
抖音扫码登录服务。
优先使用直接API（不需要浏览器），回退到Playwright+系统Chrome。
"""
from __future__ import annotations
import os
import asyncio
import yaml
import logging
import time
import sys
from pathlib import Path


def _find_chromium() -> str | None:
    """查找 Playwright 安装的 Chromium 可执行文件，支持打包后环境。"""
    try:
        from setup_check import get_chromium_path
        path = get_chromium_path()
        if path:
            return path
    except ImportError:
        pass
    home = Path.home()
    for base in [home / "AppData" / "Local" / "ms-playwright", home / ".playwright"]:
        if not base.exists():
            continue
        for item in base.iterdir():
            if item.is_dir() and ("chromium" in item.name.lower() or "chrome" in item.name.lower()):
                for exe in ["chrome-headless-shell.exe", "headless_shell.exe", "chromium-headless-shell.exe", "chrome.exe", "chromium.exe"]:
                    found = list(item.rglob(exe))
                    if found:
                        return str(found[0])
    return None


def _default_playwright_browsers_path() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    if sys.platform.startswith("win"):
        return home / "AppData" / "Local" / "ms-playwright"
    return home / ".cache" / "ms-playwright"


_SSO_PARAMS = {
    "service": "https://www.douyin.com",
    "need_logo": "false",
    "device_platform": "web_app",
    "aid": "6383",
    "account_sdk_source": "sso",
    "sdk_version": "2.2.7-beta.6",
    "language": "zh",
}
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
       "AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/130.0.0.0 Safari/537.36")
logger = logging.getLogger("app.login")


def _hidden_browser_args() -> list[str]:
    """Keep the QR fallback browser invisible even when a channel ignores defaults."""
    return [
        "--headless=new",
        "--disable-blink-features=AutomationControlled",
        "--disable-background-networking",
        "--disable-default-apps",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-features=Translate,AutomationControlled",
        "--disable-gpu",
        "--disable-popup-blocking",
        "--no-first-run",
        "--no-sandbox",
        "--window-position=-32000,-32000",
        "--window-size=1,1",
    ]


class QRLoginService:

    def __init__(self, cookies_path: str = "cookies.yaml"):
        self.cookies_path = Path(cookies_path)
        self._browser = None
        self._page = None
        self._playwright = None
        self._mode = None          # "api" or "pw"
        self._api_client = None    # httpx client for API mode
        self._api_token = ""       # token for API polling
        self._last_qr_status = "idle"
        self._api_disabled_until = 0.0

    # ── QR Code Acquisition: try direct API → Playwright ──────────────

    async def get_qrcode(self) -> dict:
        """获取登录二维码。"""
        # 方式一：直接 API。若最近已被 SSO 判定“路由已封禁”，短时间内直接走 Playwright，避免小白等待。
        if time.time() >= self._api_disabled_until:
            try:
                return await self._get_qrcode_api()
            except Exception as e:
                message = str(e)
                print(f"[QRLogin] API直调失败，切换 Playwright: {message}")
                if "路由已封禁" in message or "API返回非JSON" in message:
                    self._api_disabled_until = time.time() + 600
        else:
            print("[QRLogin] API直调近期失败，直接使用 Playwright")

        # 方式二：Playwright + Ptu 内置 Chromium/headless shell。
        # 不读取、不复用用户 Edge/Chrome 个人资料，避免把系统浏览器状态混进 Ptu。
        exe_path = _find_chromium()
        if exe_path:
            print(f"[QRLogin] 使用内置 Chromium: {exe_path}")
            return await self._get_qrcode_pw(executable_path=exe_path)

        try:
            print("[QRLogin] 使用 Playwright 隔离浏览器获取二维码")
            return await self._get_qrcode_pw()
        except Exception as e:
            raise RuntimeError(f"浏览器环境未就绪，请稍后重试（首次启动需准备 Chromium）: {e}") from e

    async def _get_qrcode_api(self) -> dict:
        """通过直接API调用获取二维码，完全不需要浏览器。"""
        import httpx

        headers = {
            "User-Agent": _UA,
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": "\"Chromium\";v=\"130\", \"Google Chrome\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "\"Windows\"",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        client = httpx.AsyncClient(follow_redirects=True, headers=headers)

        try:
            # Step 1: 访问 SSO 页面获取初始 Cookie（passport_csrf_token 等）
            await client.get(
                "https://sso.douyin.com/get_qrcode/",
                params=_SSO_PARAMS, headers=headers, timeout=6
            )

            # Step 2: 调用二维码 API
            resp = await client.get(
                "https://sso.douyin.com/passport/web/get_qrcode/",
                params=_SSO_PARAMS, headers=headers, timeout=6
            )

            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type.lower():
                body = resp.text[:120].replace("\n", " ")
                raise RuntimeError(
                    f"API返回非JSON: status={resp.status_code}, type={content_type}, body={body}"
                )
            data = resp.json()
            d = data.get("data", {})
            qr_b64 = d.get("qrcode")
            if not qr_b64:
                raise RuntimeError(f"API返回异常: {data}")

            self._api_token = d.get("token", d.get("secret", ""))
            self._last_qr_status = "waiting"
            if self._api_client:
                try:
                    await self._api_client.aclose()
                except Exception:
                    pass
            self._api_client = client
            self._mode = "api"
            print(f"[QRLogin] [OK] 通过API获取二维码成功")
            return {"qrcode": qr_b64, "token": self._api_token or "qr", "expires_in": 120}
        except Exception:
            await client.aclose()
            raise

    async def _get_qrcode_pw(
        self, channel: str | None = None, executable_path: str | None = None
    ) -> dict:
        """通过 Playwright 获取二维码。"""
        from playwright.async_api import async_playwright

        browsers_dir = str(_default_playwright_browsers_path())
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", browsers_dir)

        self._playwright = await async_playwright().start()

        launch_kwargs = {"headless": True, "args": _hidden_browser_args()}
        if channel:
            launch_kwargs["channel"] = channel
        if executable_path:
            launch_kwargs["executable_path"] = executable_path

        browser = await self._playwright.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            user_agent=_UA,
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        qr_future = asyncio.get_event_loop().create_future()

        async def on_response(resp):
            if qr_future.done():
                return
            if '/passport/web/get_qrcode' in resp.url:
                try:
                    data = await resp.json()
                    d = data.get("data", {})
                    if d.get("qrcode"):
                        token = d.get("token", d.get("secret", ""))
                        qr_future.set_result((d["qrcode"], token))
                except Exception:
                    pass

        page.on("response", on_response)

        # 反检测
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)

        url = ("https://sso.douyin.com/get_qrcode/?"
               "service=https://www.douyin.com"
               "&need_logo=false&device_platform=web_app&aid=6383"
               "&account_sdk_source=sso&sdk_version=2.2.7-beta.6&language=zh")
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)

        try:
            qr_b64, token = await asyncio.wait_for(qr_future, timeout=20)
            self._browser = browser
            self._page = page
            self._mode = "pw"
            self._api_token = token or ""
            self._last_qr_status = "waiting"
            print(f"[QRLogin] [OK] 通过Playwright获取二维码成功")
            return {"qrcode": qr_b64, "token": self._api_token or "qr", "expires_in": 120}
        except asyncio.TimeoutError:
            print(f"[QRLogin] 超时，页面URL: {page.url}")
            await self.close()
            raise RuntimeError("获取二维码超时")

    # ── Login Confirmation ────────────────────────────────────────────

    async def confirm_login(self) -> dict:
        """检查登录状态。"""
        # Playwright 模式：检查页面 cookie（原方式）
        if self._mode == "pw" and self._page:
            return await self._confirm_pw()

        # API 模式：先查本地 cookies.yaml，再尝试API轮询
        if self._check_session():
            self._last_qr_status = "done"
            return {"status": "done", "message": "登录成功"}

        if self._mode == "api":
            try:
                return await self._confirm_api()
            except Exception as e:
                print(f"[QRLogin] API轮询异常: {e}")

        return {"status": self._last_qr_status if self._last_qr_status != "idle" else "waiting",
                "message": self._status_message(self._last_qr_status)}

    async def _confirm_pw(self) -> dict:
        """检查 Playwright 页面中的登录状态。"""
        if not self._page:
            return {"status": "error", "message": "无活跃会话"}
        try:
            url = self._page.url
            cookies = await self._page.context.cookies()
            ck = {}
            for c in cookies:
                if c["name"] in ("sessionid", "sid_tt", "sid_guard",
                                 "passport_csrf_token", "odin_tt", "ttwid", "msToken"):
                    if c["value"]:
                        ck[c["name"]] = c["value"]

            if ck.get("sessionid") or ck.get("sid_tt"):
                self._save_cookies(ck)
                self._last_qr_status = "done"
                return {"status": "done", "message": "登录成功", "cookies": list(ck.keys())}

            if "login" not in url and "passport" not in url and "get_qrcode" not in url:
                if ck:
                    self._save_cookies(ck)
                    self._last_qr_status = "done"
                    return {"status": "done", "message": "登录成功", "cookies": list(ck.keys())}

            return {"status": self._last_qr_status if self._last_qr_status != "idle" else "waiting",
                    "message": self._status_message(self._last_qr_status)}
        except Exception:
            return {"status": "error", "message": "连接断开"}

    async def _confirm_api(self) -> dict:
        """通过API轮询检查登录状态（复用 _api_client 的初始 SSO cookie）。"""
        headers = {"User-Agent": _UA, "Referer": "https://www.douyin.com/"}
        client = self._api_client  # 复用初始 SSO 会话的 cookie

        if not client:
            return {"status": "error", "message": "无活跃会话"}

        # 尝试 SSO token check
        try:
            params = {"service": "https://www.douyin.com"}
            if self._api_token:
                params["token"] = self._api_token
            resp = await client.get(
                "https://sso.douyin.com/passport/web/qrcode/check",
                params=params,
                headers=headers, timeout=10
            )
            data = resp.json()
            status = self._normalize_qr_status(data.get("data", {}))
            if status != self._last_qr_status:
                logger.info("二维码登录状态: %s", status)
            self._last_qr_status = status
            if status == "done":
                return await self._exchange_cookies()
            if status in ("scanned", "expired", "error"):
                return {"status": status, "message": self._status_message(status)}
        except Exception:
            pass

        # 尝试直接访问 douyin.com 看是否有 cookie 被设置
        try:
            resp = await client.get(
                "https://www.douyin.com/",
                headers=headers, timeout=10
            )
            for c in resp.cookies:
                if c.name in ("sessionid", "sid_tt") and c.value:
                    self._save_cookies({c.name: c.value})
                    self._last_qr_status = "done"
                    return {"status": "done", "message": "登录成功", "cookies": [c.name]}
        except Exception:
                pass

        return {"status": self._last_qr_status if self._last_qr_status != "idle" else "waiting",
                "message": self._status_message(self._last_qr_status)}

    async def _exchange_cookies(self) -> dict:
        """尝试从 douyin.com 获取 session cookies（复用 _api_client）。"""
        headers = {"User-Agent": _UA, "Referer": "https://www.douyin.com/"}
        client = self._api_client
        if not client:
            import httpx
            client = httpx.AsyncClient(follow_redirects=True)
        try:
            resp = await client.get(
                "https://www.douyin.com/",
                headers=headers, timeout=10
            )
            cookies = {}
            for c in resp.cookies:
                if c.name in ("sessionid", "sid_tt", "sid_guard",
                             "ttwid", "odin_tt") and c.value:
                    cookies[c.name] = c.value
            if cookies.get("sessionid") or cookies.get("sid_tt"):
                self._save_cookies(cookies)
                self._last_qr_status = "done"
                return {"status": "done", "message": "登录成功",
                        "cookies": list(cookies.keys())}
        except Exception:
            pass
        return {"status": "waiting", "message": "等待扫码..."}

    def _normalize_qr_status(self, data: dict) -> str:
        raw = str(
            data.get("status")
            or data.get("qr_status")
            or data.get("scan_status")
            or data.get("status_code")
            or data.get("error_code")
            or ""
        ).lower()
        message = str(data.get("message") or data.get("description") or "").lower()
        combined = f"{raw} {message}"
        if raw in {"3", "done", "confirmed", "success", "login_success"}:
            return "done"
        if raw in {"2", "scanned", "scaned", "scan_success", "confirming"}:
            return "scanned"
        if raw in {"4", "expired", "timeout", "qr_expired"} or "expired" in combined or "过期" in combined:
            return "expired"
        if raw in {"5", "error", "failed", "fail"}:
            return "error"
        return "waiting"

    def _status_message(self, status: str) -> str:
        return {
            "done": "登录成功",
            "scanned": "已扫码，请在手机上确认登录",
            "expired": "二维码已过期，请刷新",
            "error": "登录状态异常，请刷新二维码",
            "waiting": "请用抖音扫描二维码",
            "idle": "请用抖音扫描二维码",
        }.get(status, "请用抖音扫描二维码")

    # ── Cookie Management ─────────────────────────────────────────────

    def _check_session(self) -> bool:
        """检查本地是否已有 session cookie。"""
        try:
            if self.cookies_path.exists():
                data = yaml.safe_load(self.cookies_path.read_text("utf-8")) or {}
                return bool(data.get("sessionid") or data.get("sid_tt"))
        except Exception:
            pass
        return False

    def _save_cookies(self, cookies: dict):
        existing = {}
        if self.cookies_path.exists():
            try:
                existing = yaml.safe_load(self.cookies_path.read_text("utf-8")) or {}
            except Exception:
                pass
        existing.update(cookies)
        needed = {"msToken": "", "ttwid": "", "odin_tt": "", "passport_csrf_token": "",
                  "sid_guard": "", "sessionid": "", "sid_tt": ""}
        needed.update(existing)
        self.cookies_path.write_text(
            yaml.dump({k: v for k, v in needed.items() if v}, allow_unicode=True), "utf-8")

    def get_status(self) -> dict:
        cookies = {}
        if self.cookies_path.exists():
            try:
                cookies = yaml.safe_load(self.cookies_path.read_text("utf-8")) or {}
            except Exception:
                pass
        logged_in = bool(cookies.get("sessionid") or cookies.get("sid_tt"))
        return {
            "logged_in": logged_in,
            "status": "logged_in" if logged_in else ("expired" if cookies else "logged_out"),
            "cookies_count": len(cookies),
        }

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._page = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


_qr_instance = None


def get_qr_service() -> QRLoginService:
    """获取 QRLoginService 单例（使用 settings 解析后的 cookies 路径）。"""
    global _qr_instance
    if _qr_instance is None:
        try:
            from ..config import settings
            path = settings.cookies_path
        except Exception:
            path = "cookies.yaml"
        _qr_instance = QRLoginService(cookies_path=path)
    return _qr_instance


qr_service = get_qr_service()
