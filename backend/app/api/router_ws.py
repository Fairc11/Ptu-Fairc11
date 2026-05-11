from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..services.progress import progress_emitter

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(ws: WebSocket, client_id: str):
    """WebSocket for real-time progress updates."""
    await progress_emitter.connect(client_id, ws)
    try:
        while True:
            # Keep connection alive, wait for client messages
            await ws.receive_text()
    except WebSocketDisconnect:
        progress_emitter.disconnect(client_id)
