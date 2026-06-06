from __future__ import annotations

from backend.app.services.downloader import DownloadManager


def test_douyin_video_url_with_mime_type_query_saves_as_mp4():
    manager = DownloadManager()

    ext = manager._guess_extension(
        "https://v26-web.douyinvod.com/video/tos/cn/example/"
        "?a=6383&mime_type=video_mp4&__vid=7567584265539833114"
    )

    assert ext == ".mp4"


def test_douyin_video_url_with_path_hint_saves_as_mp4():
    manager = DownloadManager()

    ext = manager._guess_extension(
        "https://v11-weba.douyinvod.com/abc/video/tos/cn/tos-cn-ve-15/example/?a=6383"
    )

    assert ext == ".mp4"
