import asyncio
import json
import logging
import websockets
from typing import Set, Dict, Any, Optional, List
import time

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
        Broadcast a message to all connected clients concurrently.
        
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
                
            # --- Measure Serialization Time --- Start
            serialization_start_time = time.monotonic()
            # Convert to JSON if it's not already a string
            if not isinstance(message, str):
                message_json = json.dumps(message)
            else:
                message_json = message # Already a string
            serialization_end_time = time.monotonic()
            serialization_duration = serialization_end_time - serialization_start_time
            # Log serialization time periodically or if it exceeds a threshold
            # Using simple periodic logging for now (e.g., every 60 calls ~ 1s at 60fps)
            # A counter could be added to the class if more precise periodic logging is needed
            if message.get("type") == "smpl_update" and logger.isEnabledFor(logging.DEBUG): # Check level
                if getattr(self, '_broadcast_count', 0) % 60 == 0:
                    logger.debug(f"JSON serialization took: {serialization_duration:.6f} seconds")
                self._broadcast_count = getattr(self, '_broadcast_count', 0) + 1
            # --- Measure Serialization Time --- End
        except Exception as e:
            logger.error(f"Error serializing message: {str(e)}")
            return

        # Prepare tasks for concurrent sending
        tasks = []
        stale_connections = set()
        valid_clients_for_broadcast = []

        for websocket in list(self.connected_clients):
            # Skip the originating websocket
            if originating_websocket and websocket == originating_websocket:
                continue

            # Skip closed connections immediately
            if hasattr(websocket, 'closed') and websocket.closed:
                 logger.debug("Skipping closed connection before creating task")
                 stale_connections.add(websocket)
                 continue
            
            # Add valid client and create send task
            valid_clients_for_broadcast.append(websocket)
            tasks.append(self._send_individual_message(websocket, message_json))

        if not tasks:
            logger.debug("No valid clients to broadcast to.")
             # Still process any stale connections found
            for ws in stale_connections:
                 self.remove_client(ws)
            return

        # Run tasks concurrently and gather results
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and identify failures/stale connections
        success_count = 0
        failed_count = 0
        for i, result in enumerate(results):
            client_ws = valid_clients_for_broadcast[i] # Get corresponding websocket
            if isinstance(result, Exception):
                logger.warning(f"Error sending message to client {client_ws.remote_address}: {result}")
                stale_connections.add(client_ws)
                failed_count += 1
            elif result is False: # Our helper function returns False on specific non-exception errors
                # This case might be redundant if _send_individual_message raises exceptions for failures
                 logger.warning(f"Failed to send to client {client_ws.remote_address} (reported by send function)")
                 stale_connections.add(client_ws)
                 failed_count += 1
            else:
                success_count += 1

        # Remove stale connections identified during broadcast or pre-check
        if stale_connections:
             logger.info(f"Removing {len(stale_connections)} stale connections identified during broadcast.")
             for ws in stale_connections:
                 self.remove_client(ws)

        if failed_count > 0:
            logger.info(f"Broadcast complete - {success_count} succeeded, {failed_count} failed")
        # else: # Optional: Log success only if needed
        #     logger.debug(f"Broadcast complete - {success_count} succeeded")

    async def _send_individual_message(self, websocket: websockets.WebSocketServerProtocol, message: str) -> bool:
        """Helper coroutine to send a message to one client, handling exceptions."""
        try:
             # Re-check closed status just before sending, though unlikely to change
             if hasattr(websocket, 'closed') and websocket.closed:
                  # Raise exception to be caught by gather
                  raise websockets.exceptions.ConnectionClosedOK(1000, "Client connection closed before send")
             await websocket.send(message)
             return True
        except Exception as e:
             # Raise the exception so asyncio.gather captures it
             raise e

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