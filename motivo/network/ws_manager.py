import asyncio
import json
import logging
import websockets
from typing import Set, Dict, Any

logger = logging.getLogger('network')

class WebSocketManager:
    """WebSocket connection manager for broadcasting messages to clients"""
    
    def __init__(self):
        """Initialize the WebSocket manager"""
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        logger.info("WebSocket manager initialized")

    async def broadcast(self, message: Dict[Any, Any]) -> None:
        """
        Broadcast a message to all connected clients
        
        Args:
            message: The message to broadcast, either a string or a dict that will be converted to JSON
        """
        if not self.connected_clients:
            logger.debug("No clients connected, broadcast skipped")
            return
            
        try:
            # Convert to JSON if it's not already a string
            if not isinstance(message, str):
                message = json.dumps(message)
        except Exception as e:
            logger.error(f"Error serializing message: {str(e)}")
            return

        # Use a list to avoid "set changed size during iteration" errors
        success_count = 0
        failed_count = 0
        stale_connections = set()
        
        for websocket in list(self.connected_clients):
            try:
                # Check if connection is closed before attempting to send
                if hasattr(websocket, 'closed') and websocket.closed:
                    logger.debug("Skipping closed connection")
                    stale_connections.add(websocket)
                    failed_count += 1
                    continue
                    
                await websocket.send(message)
                success_count += 1
            except Exception as e:
                logger.warning(f"Error sending message to client: {str(e)}")
                # Remove the client if there was an error
                stale_connections.add(websocket)
                failed_count += 1
        
        # Remove stale connections outside the loop
        for ws in stale_connections:
            self.connected_clients.discard(ws)
                
        if failed_count > 0:
            logger.info(f"Broadcast complete - {success_count} succeeded, {failed_count} failed")

    def get_stats(self) -> Dict[str, int]:
        """
        Get current connection statistics
        
        Returns:
            Dict with connection statistics
        """
        return {
            "connected_clients": len(self.connected_clients)
        }