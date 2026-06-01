from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from backend.app.models.schemas import MediaType
from backend.app.services.scraper import DouyinScraper


def make_scraper(monkeypatch: pytest.MonkeyPatch) -> DouyinScraper:
    monkeypatch.setattr(
        "backend.app.services.scraper.ensure_ttwid",
        lambda cookies: cookies,
    )
    return DouyinScraper(cookies_path="__missing_test_cookies__.yaml")


def test_extract_profile_sec_uid_from_share_text_and_resolved_short_link(monkeypatch):
    scraper = make_scraper(monkeypatch)
    sec_uid = "MS4wLjABAAAAuLGv9nn8hGijUBf0u1ITnJKu3tSlny25c7SfYdNKf1v9MZWQk5ARN7iR7mEFzwGl"

    def fake_resolve(url: str) -> str:
        assert url == "https://v.douyin.com/vAjDKDovzq8/"
        return f"https://www.douyin.com/user/{sec_uid}?from_tab_name=main"

    monkeypatch.setattr(scraper, "_resolve_url", fake_resolve)

    raw = (
        "7- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 "
        "https://v.douyin.com/vAjDKDovzq8/ 0@0.com :0pm"
    )

    parsed = scraper._extract_profile_sec_uid(raw)

    assert parsed.sec_uid == sec_uid
    assert parsed.input_url == "https://v.douyin.com/vAjDKDovzq8/"
    assert parsed.resolved_url == f"https://www.douyin.com/user/{sec_uid}?from_tab_name=main"


def test_extract_profile_sec_uid_rejects_single_aweme_link(monkeypatch):
    scraper = make_scraper(monkeypatch)
    raw = "https://www.douyin.com/video/7499444619563142460"

    with pytest.raises(ValueError, match="作品链接"):
        scraper._extract_profile_sec_uid(raw)


def test_profile_api_url_contains_browser_context_and_cookie_tokens(monkeypatch):
    scraper = make_scraper(monkeypatch)
    scraper.cookies = {
        "sessionid": "session-test",
        "ttwid": "ttwid-test",
        "msToken": "token-test",
    }

    url, headers = scraper._build_profile_api_request(
        "https://www.douyin.com/aweme/v1/web/aweme/post/",
        "MS4wLjABAAAAprofile",
        max_cursor=20,
        count=20,
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert query["sec_user_id"] == ["MS4wLjABAAAAprofile"]
    assert query["max_cursor"] == ["20"]
    assert query["count"] == ["20"]
    assert query["device_platform"] == ["webapp"]
    assert query["channel"] == ["channel_pc_web"]
    assert query["pc_client_type"] == ["1"]
    assert query["browser_name"]
    assert query["browser_version"]
    assert query["msToken"] == ["token-test"]
    assert "sessionid=session-test" in headers["Cookie"]
    assert "ttwid=ttwid-test" in headers["Cookie"]


def test_parse_video_detail_keeps_create_time(monkeypatch):
    scraper = make_scraper(monkeypatch)

    result = scraper._parse_detail_to_result(
        {
            "desc": "video title",
            "create_time": 1711111111,
            "author": {"nickname": "author"},
            "video": {
                "play_addr": {"url_list": ["https://example.test/video.mp4"]},
                "cover": {"url_list": ["https://example.test/cover.jpg"]},
            },
        },
        page_url="https://www.douyin.com/video/7639628294337437361",
    )

    assert result is not None
    assert result.media_type == MediaType.VIDEO
    assert result.music_url == "https://example.test/video.mp4"
    assert result.image_urls == ["https://example.test/cover.jpg"]
    assert result.create_time == 1711111111
