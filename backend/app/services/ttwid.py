"""ttwid token acquisition for Douyin API access.

The ttwid cookie is required for Douyin API requests.
It can be obtained without login via ByteDance's registration endpoint.
"""
from __future__ import annotations
import json
import httpx
from http import cookies as http_cookies


def get_ttwid() -> str | None:
    """Obtain a ttwid from ByteDance's registration endpoint."""
    url = "https://ttwid.bytedance.com/ttwid/union/register/"
    payload = {
        "region": "cn",
        "aid": 1768,
        "needFid": False,
        "service": "www.ixigua.com",
        "migrate_info": {"ticket": "", "source": "node"},
        "cburl_protocol": "https",
        "union": True,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/130.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(follow_redirects=True) as client:
            resp = client.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                set_cookie = resp.headers.get("Set-Cookie")
                if set_cookie:
                    simple_cookie = http_cookies.SimpleCookie(set_cookie)
                    if "ttwid" in simple_cookie:
                        return simple_cookie["ttwid"].value
    except Exception as e:
        print(f"[ttwid] 获取失败: {e}")

    return None


def ensure_ttwid(cookies: dict[str, str]) -> dict[str, str]:
    """Ensure ttwid is in cookies dict, fetching if needed."""
    if "ttwid" in cookies and cookies["ttwid"]:
        return cookies
    ttwid = get_ttwid()
    if ttwid:
        cookies["ttwid"] = ttwid
        print(f"[ttwid] 成功获取 ttwid: {ttwid[:20]}...")
    return cookies
