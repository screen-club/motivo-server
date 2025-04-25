import logging
from datetime import datetime
import json
import traceback

from core.state import app_state

logger = logging.getLogger('webrtc')

async def handle_webrtc_offer(websocket, data):
    """
    Handle WebRTC offer from client
    Simple implementation using aiortc library
    """
    client_id = data.get("client_id")
    sdp = data.get("sdp")
    
    if not client_id or not sdp:
        logger.warning("Invalid WebRTC offer: missing client_id or sdp")
        if not websocket.closed:
            try:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "invalid_offer",
                    "message": "Missing client_id or sdp in offer",
                    "client_id": client_id,
                    "timestamp": datetime.now().isoformat()
                }))
            except Exception as e:
                logger.warning(f"Could not send error to client: {e}")
        return
    
    logger.info(f"Processing WebRTC offer from client {client_id}")
    
    try:
        # Create offer object
        offer = {
            "type": "offer",
            "sdp": sdp
        }
        
        # Process offer and create answer
        answer = await app_state.webrtc_manager.create_peer_connection(client_id, offer)
        
        if not answer:
            raise Exception("Failed to create peer connection")
        
        # Send answer to client
        if not websocket.closed:
            await websocket.send(json.dumps({
                "type": "webrtc_answer",
                "sdp": answer["sdp"],
                "sdpType": answer["type"],
                "client_id": client_id,
                "timestamp": datetime.now().isoformat()
            }))
            logger.info(f"Sent WebRTC answer to client {client_id}")
            
            # Send connection stats
            await websocket.send(json.dumps({
                "type": "webrtc_stats",
                "stats": app_state.webrtc_manager.get_connection_stats(),
                "client_id": client_id,
                "timestamp": datetime.now().isoformat()
            }))
        
    except Exception as e:
        logger.error(f"Error handling WebRTC offer: {e}")
        traceback.print_exc()
        
        # Send error to client
        if not websocket.closed:
            try:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "connection_failed",
                    "message": f"Failed to create WebRTC connection: {str(e)}",
                    "client_id": client_id,
                    "timestamp": datetime.now().isoformat()
                }))
            except Exception as send_err:
                logger.warning(f"Could not send error message: {send_err}")

async def handle_ice_candidate(websocket, data):
    """
    Handle ICE candidate from client
    Simple implementation using aiortc library
    """
    client_id = data.get("client_id")
    candidate_dict = data.get("candidate")
    
    if not client_id:
        logger.warning("Invalid ICE candidate: missing client_id")
        return
    
    # Handle empty candidate (normal for end-of-candidates)
    if not candidate_dict:
        logger.debug(f"Received empty ICE candidate for client {client_id}")
        return
    
    logger.debug(f"Received ICE candidate for client {client_id}")

    try:
        # Add candidate to WebRTC manager
        result = await app_state.webrtc_manager.add_ice_candidate(client_id, candidate_dict)
        
        if result:
            logger.debug(f"Successfully added ICE candidate for client {client_id}")
        else:
            logger.debug(f"Could not add ICE candidate for client {client_id}")
            
    except Exception as e:
        logger.error(f"Error handling ICE candidate: {e}")
        traceback.print_exc()