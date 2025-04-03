import asyncio
import json
import logging
import websockets
from typing import Set, Dict, Any, Optional, List

logger = logging.getLogger('network')

class WebSocketManager:
    """WebSocket connection manager for broadcasting messages to clients"""
    
    def __init__(self):
        """Initialize the WebSocket manager"""
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        # Track clients by IP address to detect duplicates
        self.client_connections: Dict[str, List[websockets.WebSocketServerProtocol]] = {}
        # Track recently sent message IDs to prevent echo
        self.recent_message_ids = set()
        self.max_message_ids = 1000
        logger.debug("WebSocket manager initialized")
    
    def add_client(self, websocket):
        """Add a client to the manager with proper tracking"""
        self.connected_clients.add(websocket)
        
        # Get the client IP
        client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else "unknown"
        
        # Add to IP-based tracking
        if client_ip not in self.client_connections:
            self.client_connections[client_ip] = []
        
        self.client_connections[client_ip].append(websocket)
        
        # Log connections from this IP
        if len(self.client_connections[client_ip]) > 1:
            logger.warning(f"Multiple connections ({len(self.client_connections[client_ip])}) from IP {client_ip}")
        
        return client_ip
    
    def remove_client(self, websocket):
        """Remove a client from the manager"""
        self.connected_clients.discard(websocket)
        
        # Also remove from IP-based tracking
        client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else "unknown"
        
        if client_ip in self.client_connections:
            if websocket in self.client_connections[client_ip]:
                self.client_connections[client_ip].remove(websocket)
            
            # Remove the IP entry if no more connections
            if not self.client_connections[client_ip]:
                del self.client_connections[client_ip]
    
    async def send_to_client(self, websocket, message):
        """Send a message to a specific client"""
        if not websocket or (hasattr(websocket, 'closed') and websocket.closed):
            return False
            
        try:
            # Convert to JSON if it's not already a string
            if not isinstance(message, str):
                message = json.dumps(message)
                
            await websocket.send(message)
            return True
        except Exception as e:
            logger.warning(f"Error sending message to client: {str(e)}")
            return False

    async def broadcast(self, message: Dict[Any, Any], originating_websocket: Optional[websockets.WebSocketServerProtocol] = None) -> None:
        """
        Broadcast a message to all connected clients
        
        Args:
            message: The message to broadcast, either a string or a dict that will be converted to JSON
            originating_websocket: The websocket that originated this message (to prevent echoes)
        """
        if not self.connected_clients:
            logger.debug("No clients connected, broadcast skipped")
            return
            
        try:
            # Track message ID if available to prevent echo
            message_id = message.get("message_id", None) if isinstance(message, dict) else None
            
            if message_id:
                # Skip if we've seen this message ID recently
                if message_id in self.recent_message_ids:
                    logger.debug(f"Skipping duplicate message ID: {message_id}")
                    return
                
                # Add to recent messages
                self.recent_message_ids.add(message_id)
                # Trim if necessary
                if len(self.recent_message_ids) > self.max_message_ids:
                    self.recent_message_ids = set(list(self.recent_message_ids)[-self.max_message_ids//2:])
                
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
            # Skip the originating websocket to prevent echo
            if originating_websocket and websocket == originating_websocket:
                continue
                
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
            self.remove_client(ws)
                
        if failed_count > 0:
            logger.info(f"Broadcast complete - {success_count} succeeded, {failed_count} failed")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current connection statistics
        
        Returns:
            Dict with connection statistics
        """
        # Count unique IP addresses
        unique_ips = len(self.client_connections)
        
        # Count connections by IP
        connections_by_ip = {ip: len(conns) for ip, conns in self.client_connections.items()}
        
        return {
            "connected_clients": len(self.connected_clients),
            "unique_clients": unique_ips,
            "connections_by_ip": connections_by_ip
        }