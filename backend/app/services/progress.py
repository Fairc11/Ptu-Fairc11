from __future__ import annotations
from fastapi import WebSocket, WebSocketDisconnect
from ..models.schemas import DownloadProgress


class ProgressEmitter:
    """Manages WebSocket connections and broadcasts progress updates."""

    def __init__(self):
        self.connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, ws: WebSocket):
        await ws.accept()
        self.connections[client_id] = ws

    def disconnect(self, client_id: str):
        self.connections.pop(client_id, None)

    async def emit(self, client_id: str, data: DownloadProgress):
        ws = self.connections.get(client_id)
        if ws:
            try:
                await ws.send_json(data.model_dump())
            except WebSocketDisconnect:
                self.disconnect(client_id)

    async def emit_stage(self, client_id: str, stage: str, progress: float,
                         message: str = "", current: int = 0, total: int = 0):
        await self.emit(client_id, DownloadProgress(
            task_id=client_id,
            stage=stage,
            progress=progress,
            message=message,
            current_item=current,
            total_items=total,
        ))


progress_emitter = ProgressEmitter()
