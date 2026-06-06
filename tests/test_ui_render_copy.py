from __future__ import annotations

from pathlib import Path


def test_render_ui_uses_clear_vertical_video_copy():
    html = Path("backend/app/templates/index.html").read_text(encoding="utf-8")
    js = Path("backend/app/static/js/app.js").read_text(encoding="utf-8")

    assert "生成竖屏视频" in html
    assert "生成视频" in html
    assert "准备生成竖屏视频" in js
    assert "竖屏视频生成完成" in js
    assert "已保存到素材文件夹" in js
    assert "打开视频" in js
    assert "复制路径" in html
    assert "music_duration_seconds" in js
    assert "cycle_count" in js
    assert "id=\"transition\"" not in html
    assert "id=\"image-duration\"" not in html
    assert "image_duration: 2.6" in js
    assert "transition_duration: 0.28" in js
    assert "live_photo_mode: 'video'" in js


def test_progress_and_browser_copy_ui_match_v15_polish():
    html = Path("backend/app/templates/index.html").read_text(encoding="utf-8")
    js = Path("backend/app/static/js/app.js").read_text(encoding="utf-8")

    assert html.index('id="result-section"') < html.index('id="progress-section"')
    assert "复制当前链接" not in html
    assert "手动复制链接" in html
    assert "browser-login-panel" in html
    assert "browser-native-host" in html
    assert "login-modal" not in html
    assert "copyBrowserUrl" not in js
    assert "force_reload=True" not in js
