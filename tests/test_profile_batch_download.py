from __future__ import annotations

from pathlib import Path

from backend.app.api.router_profile import MAX_PROFILE_POSTS, _result_from_profile_post
from backend.app.models.schemas import MediaType


def test_result_from_profile_video_post_uses_embedded_download_url():
    result = _result_from_profile_post(
        {
            "aweme_id": "7639628294337437361",
            "desc": "video title",
            "media_type": "video",
            "cover_url": "https://example.test/cover.jpg",
            "image_urls": ["https://example.test/cover.jpg"],
            "video_url": "https://example.test/video.mp4",
            "music_url": "https://example.test/music.mp3",
            "music_title": "music title",
            "create_time": 1711111111,
        },
        "沈月",
    )

    assert result is not None
    assert result.media_type == MediaType.VIDEO
    assert result.music_url == "https://example.test/video.mp4"
    assert result.image_urls == ["https://example.test/cover.jpg"]
    assert result.author == "沈月"
    assert result.aweme_id == "7639628294337437361"
    assert result.create_time == 1711111111
    assert result.text_content == "video title"


def test_result_from_profile_image_post_uses_embedded_images_and_music():
    result = _result_from_profile_post(
        {
            "aweme_id": "123",
            "desc": "image title",
            "media_type": "image",
            "image_urls": ["https://example.test/1.jpg", "https://example.test/2.jpg"],
            "music_url": "https://example.test/music.mp3",
            "music_title": "music title",
        },
        "作者",
    )

    assert result is not None
    assert result.media_type == MediaType.IMAGE_SET
    assert result.image_urls == ["https://example.test/1.jpg", "https://example.test/2.jpg"]
    assert result.music_url == "https://example.test/music.mp3"
    assert result.text_content == "image title"


def test_result_from_profile_live_post_preserves_desc_for_post_txt():
    result = _result_from_profile_post(
        {
            "aweme_id": "live-123",
            "desc": "live photo caption",
            "media_type": "image",
            "image_urls": ["https://example.test/1.jpg"],
            "music_url": "https://example.test/music.mp3",
            "live_photo_data": [
                {
                    "image_url": "https://example.test/1.jpg",
                    "video_url": "https://example.test/1.mp4",
                }
            ],
        },
        "作者",
    )

    assert result is not None
    assert result.media_type == MediaType.LIVE_PHOTO
    assert result.text_content == "live photo caption"


def test_profile_scrape_uses_low_risk_default_limit():
    js = Path("backend/app/static/js/app.js").read_text(encoding="utf-8")

    assert MAX_PROFILE_POSTS == 30
    assert "max_posts: 30" in js
    assert "max_posts: 500" not in js
    assert "max_cursor: state.profileNextCursor" in js
    assert "下一批 30 个" in Path("backend/app/templates/index.html").read_text(encoding="utf-8")
