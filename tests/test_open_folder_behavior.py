from __future__ import annotations

import pytest

from backend.app.main import open_folder
from backend.app.models.schemas import TaskInfo


@pytest.mark.asyncio
async def test_open_folder_opens_output_parent_not_video_file(tmp_path, monkeypatch):
    output_file = tmp_path / "douyin_slideshow.mp4"
    output_file.write_bytes(b"fake-video")
    task = TaskInfo(
        task_id="task-open",
        share_url="https://example.test",
        output_path=str(output_file),
    )

    class FakeStore:
        def get(self, task_id):
            return task

    opened = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            opened.append((args, kwargs))

    import backend.app.models.task_store as task_store

    monkeypatch.setattr(task_store, "store", FakeStore())
    monkeypatch.setattr("subprocess.Popen", FakePopen)

    response = await open_folder("task-open")

    assert response["opened"] == [str(tmp_path)]
    assert opened == [(["explorer", str(tmp_path)], {})]
