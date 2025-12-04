from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from server.app.core.realtime import get_connection_manager
from server.app.core.security import CurrentUser, get_current_user_ws

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    current_user: CurrentUser = Depends(get_current_user_ws),
) -> None:
    manager = get_connection_manager()
    user_id = current_user.id
    await manager.connect(user_id, websocket)
    try:
        while True:
            # We currently do not rely on messages from client; this keeps the
            # connection open and allows for future ping/commands if needed.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)

