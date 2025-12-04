from __future__ import annotations

from typing import Any, Dict, List

from starlette.websockets import WebSocket

from server.app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)
        logger.info("WebSocket connected", extra={"user_id": user_id, "connections": len(self._connections[user_id])})

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(user_id)
        if not conns:
            return
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(user_id, None)
        logger.info("WebSocket disconnected", extra={"user_id": user_id})

    async def send_to_user(self, user_id: str, message: Dict[str, Any]) -> None:
        conns = self._connections.get(user_id, [])
        if not conns:
            return
        for ws in list(conns):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                try:
                    await ws.close()
                except Exception:  # noqa: BLE001
                    pass
                self.disconnect(user_id, ws)


_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    return _manager


async def send_event_to_user(user_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    """Helper used by routes/services to push a typed event to a user."""
    if not user_id:
        return
    await _manager.send_to_user(
        user_id,
        {
            "type": event_type,
            "payload": payload,
        },
    )

