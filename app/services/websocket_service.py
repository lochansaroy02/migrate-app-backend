"""
WebSocket service — thin adapter between the ws_manager singleton and the API layer.
"""

from fastapi import WebSocket

from app.websockets.manager import ws_manager


class WebSocketService:
    async def handle_migration_ws(self, migration_id: str, ws: WebSocket) -> None:
        await ws_manager.connect(migration_id, ws)
        try:
            while True:
                # Keep connection alive; client can send pings or disconnect
                data = await ws.receive_text()
                if data == "ping":
                    await ws.send_text("pong")
        except Exception:
            pass
        finally:
            await ws_manager.disconnect(migration_id, ws)


websocket_service = WebSocketService()
