import json
import time
import asyncio
import websockets
from datetime import datetime
import logging

from core.state import app_state
from core.config import config

logger = logging.getLogger('network')

async def handle_websocket(websocket):
    """Handle a new WebSocket connection with improved robustness"""
    # Get client information for logging
    client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}" if hasattr(websocket, 'remote_address') else "Unknown"
    logger.info(f"New WebSocket connection from {client_info}")
    
    # Generate a unique client ID
    client_id = f"{client_info}_{int(time.time() * 1000)}"
    
    # Add custom attributes for better tracking
    websocket.client_id = client_id
    websocket.connection_time = time.time()
    if not hasattr(websocket, 'closed'):
        websocket.closed = False
    
    # Add to connected clients
    client_ip = app_state.ws_manager.add_client(websocket)
    logger.debug(f"Total connections: {len(app_state.ws_manager.connected_clients)}, unique clients: {len(app_state.ws_manager.client_connections)}")
    
    # Configure WebSocket connection with longer ping timeout
    if hasattr(websocket, 'protocol'):
        websocket.protocol.ping_timeout = 60  # Increase ping timeout to 60 seconds
    
    try:
        # Send welcome message
        await send_welcome_message(websocket, client_id)
        
        # Handle incoming messages
        async for message in websocket:
            await process_message(websocket, message, client_info)
                
    except websockets.exceptions.ConnectionClosed as e:
        logger.debug(f"Client {client_info} disconnected: {str(e)}")
        websocket.closed = True
    except Exception as e:
        logger.error(f"Error in websocket handler for {client_info}: {str(e)}")
        websocket.closed = True
    finally:
        # Ensure closed attribute is set
        websocket.closed = True
        await handle_client_disconnect(websocket, client_info)

async def send_welcome_message(websocket, client_id):
    """Send welcome message to newly connected client"""
    try:
        welcome_msg = {
            "type": "connection_established",
            "message": "Successfully connected to WebSocket server",
            "timestamp": datetime.now().isoformat(),
            "client_id": client_id,
            "server_info": {
                "backend_domain": config.backend_domain,
                "ws_port": config.ws_port
            }
        }
        await websocket.send(json.dumps(welcome_msg))
    except Exception as e:
        logger.error(f"Error sending welcome message: {str(e)}")

async def process_message(websocket, message, client_info):
    """Process an incoming WebSocket message with improved routing"""
    try:
        data = json.loads(message)
        message_type = data.get("type", "")
        
        # Route to appropriate handler based on message type
        if message_type == "webrtc_offer":
            # Import here to avoid circular imports
            from network.webrtc_handlers import handle_webrtc_offer
            await handle_webrtc_offer(websocket, data)
        elif message_type == "ping":
            await handle_ping(websocket)
        elif message_type == "set_video_quality":
            await handle_video_quality(websocket, data)
        elif message_type == "ice_candidate" or message_type == "webrtc_ice":
            # Import here to avoid circular imports
            from network.webrtc_handlers import handle_ice_candidate
            await handle_ice_candidate(websocket, data)
        else:
            # Handle all other message types through message handler
            await app_state.message_handler.handle_message(websocket, message)
            
    except json.JSONDecodeError:
        # Handle non-JSON messages through message handler
        await app_state.message_handler.handle_message(websocket, message)

async def handle_ping(websocket):
    """Handle ping messages from client"""
    await websocket.send(json.dumps({
        "type": "pong",
        "timestamp": datetime.now().isoformat()
    }))

async def handle_video_quality(websocket, data):
    """Handle video quality change requests"""
    client_id = data.get("client_id")
    quality = data.get("quality")
    
    if quality and hasattr(app_state.webrtc_manager, 'set_video_quality'):
        # Note about Docker performance
        if config.in_container and quality not in ["low", "medium"]:
            logger.warning(f"In Docker: Received request for {quality} quality, consider using 'low' or 'medium' if video fails")
            
        success = app_state.webrtc_manager.set_video_quality(quality)
        
        # Send confirmation with more details
        try:
            # Include available quality options in response
            quality_options = list(app_state.webrtc_manager.video_config.keys()) if hasattr(app_state.webrtc_manager, 'video_config') else []
            
            await websocket.send(json.dumps({
                "type": "video_quality_changed",
                "quality": quality,
                "success": success,
                "client_id": client_id,
                "available_qualities": quality_options,
                "timestamp": datetime.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending quality change confirmation: {e}")
    else:
        logger.warning(f"Invalid quality '{quality}' or WebRTC manager not initialized")
        try:
            await websocket.send(json.dumps({
                "type": "video_quality_changed",
                "quality": quality,
                "success": False,
                "error": "Invalid quality or WebRTC manager not initialized",
                "client_id": client_id,
                "timestamp": datetime.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending quality change error: {e}")

async def handle_client_disconnect(websocket, client_info):
    """Clean up after client disconnection"""
    # Ensure the closed attribute is set
    if hasattr(websocket, 'closed'):
        websocket.closed = True
    
    # Clean up WebRTC connections
    try:
        client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else None
        if client_ip and hasattr(app_state, 'webrtc_manager') and app_state.webrtc_manager:
            # Check all current WebRTC connections and close matching ones
            for client_id in list(app_state.webrtc_manager.peer_connections.keys()):
                # Check if client ID contains the IP address (our naming convention)
                if client_ip in client_id or (hasattr(websocket, 'client_id') and websocket.client_id in client_id):
                    # Create separate task to avoid blocking
                    asyncio.create_task(app_state.webrtc_manager.close_connection(client_id))
                    logger.debug(f"Scheduled WebRTC cleanup for client {client_id}")
    except Exception as e:
        logger.error(f"Error during WebRTC cleanup: {str(e)}")
        
    # Remove from connected clients
    app_state.ws_manager.remove_client(websocket)
    logger.info(f"Client disconnected. Total connections: {len(app_state.ws_manager.connected_clients)}, unique clients: {len(app_state.ws_manager.client_connections)}")