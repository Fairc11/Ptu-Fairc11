from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from .schemas import TaskInfo, TaskStatus, ScrapeResult


class TaskStore:
    """Simple JSON-file-backed task store."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._tasks: dict[str, TaskInfo] = {}
        self._load()

    def _load(self):
        if self.db_path.exists():
            try:
                data = json.loads(self.db_path.read_text("utf-8"))
                for item in data:
                    task = TaskInfo(**item)
                    self._tasks[task.task_id] = task
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        data = [t.model_dump(mode="json") for t in self._tasks.values()]
        self.db_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    def create(self, share_url: str) -> TaskInfo:
        task = TaskInfo(share_url=share_url)
        self._tasks[task.task_id] = task
        self._save()
        return task

    def get(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def update_status(self, task_id: str, status: TaskStatus, **kwargs):
        task = self._tasks.get(task_id)
        if task:
            task.status = status
            task.updated_at = datetime.now()
            for k, v in kwargs.items():
                if hasattr(task, k):
                    setattr(task, k, v)
            self._save()

    def update_metadata(self, task_id: str, metadata: ScrapeResult):
        task = self._tasks.get(task_id)
        if task:
            task.metadata = metadata
            task.updated_at = datetime.now()
            self._save()

    def list_tasks(self) -> list[TaskInfo]:
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    def delete(self, task_id: str):
        self._tasks.pop(task_id, None)
        self._save()


store: Optional[TaskStore] = None


def get_store() -> TaskStore:
    assert store is not None, "TaskStore not initialized"
    return store
