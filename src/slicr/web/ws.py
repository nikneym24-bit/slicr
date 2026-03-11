"""
WebSocket для трансляции логов в реальном времени.

Подключение: ws://<IP>:8080/ws/logs
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from slicr.web.state import AppState

logger = logging.getLogger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    """Стрим логов через WebSocket."""
    await websocket.accept()
    state: AppState = websocket.app.state.app_state
    log_queue = state.subscribe_logs()

    try:
        while True:
            msg = await log_queue.get()
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket закрыт: %s", e)
    finally:
        state.unsubscribe_logs(log_queue)
