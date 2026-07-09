import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps user_id (str) to a list of active WebSockets (since a user can have multiple tabs open)
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"WebSocket connected for user: {user_id}. Active connections: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
                logger.info(f"WebSocket disconnected for user: {user_id}")
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: str):
        """Sends a JSON message to all active WebSocket connections of a specific user."""
        if user_id in self.active_connections:
            disconnected_websockets = []
            for websocket in self.active_connections[user_id]:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending WebSocket message to user {user_id}: {str(e)}")
                    disconnected_websockets.append(websocket)
            
            # Clean up any dead connections found during sending
            for ws in disconnected_websockets:
                self.disconnect(user_id, ws)

manager = ConnectionManager()
