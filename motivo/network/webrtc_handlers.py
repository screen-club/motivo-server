import asyncio
import logging
from aiortc import RTCIceCandidate
from datetime import datetime
import json
import traceback

from core.state import app_state

logger = logging.getLogger('webrtc')

async def handle_webrtc_offer(websocket, data):
    """Handle WebRTC offer from client"""
    client_id = data.get("client_id")
    sdp = data.get("sdp")
    
    if not client_id or not sdp:
        logger.warning("Invalid WebRTC offer: missing client_id or sdp")
        # Send error response to client
        await websocket.send(json.dumps({
            "type": "error",
            "error": "invalid_offer",
            "message": "Missing client_id or sdp in offer",
            "client_id": client_id,
            "timestamp": datetime.now().isoformat()
        }))
        return
        
    logger.debug(f"Processing WebRTC offer from client {client_id}")
    
    try:
        # Log information about the offer
        logger.debug(f"Received WebRTC offer from client {client_id}")
        
        # Create offer object in the expected format
        offer = {
            "type": "offer",
            "sdp": sdp
        }
        
        # Process offer without enforcing a tight timeout
        answer = await app_state.webrtc_manager.create_peer_connection(client_id, offer)
        
        if not answer:
            raise Exception("Failed to create peer connection")
        
        # Send the answer back
        await websocket.send(json.dumps({
            "type": "webrtc_answer",
            "sdp": answer["sdp"],
            "sdpType": answer["type"],
            "client_id": client_id,
            "timestamp": datetime.now().isoformat()
        }))
        logger.debug(f"Sent WebRTC answer to client {client_id}")
        
        # Send connection stats for debugging
        stats = app_state.webrtc_manager.get_connection_stats()
        await websocket.send(json.dumps({
            "type": "webrtc_stats",
            "stats": stats,
            "client_id": client_id,
            "timestamp": datetime.now().isoformat()
        }))
            
    except Exception as e:
        logger.error(f"Error handling WebRTC offer: {str(e)}")
        traceback.print_exc()
        
        # Send error response to client
        await websocket.send(json.dumps({
            "type": "error",
            "error": "connection_failed",
            "message": f"Failed to create WebRTC connection: {str(e)}",
            "client_id": client_id,
            "timestamp": datetime.now().isoformat()
        }))

async def handle_ice_candidate(websocket, data):
    """Handle ICE candidate message from client"""
    client_id = data.get("client_id")
    candidate_dict = data.get("candidate")
    
    if not client_id:
        logger.warning("Invalid ICE candidate: missing client_id")
        return
    
    # Handle empty candidate case gracefully - this is normal for end-of-candidates
    if not candidate_dict or (isinstance(candidate_dict, dict) and not candidate_dict.get("candidate", "")):
        logger.debug(f"Received empty ICE candidate for client {client_id} - likely end-of-candidates")
        return
    
    # Check if candidate is valid before logging detailed message
    if isinstance(candidate_dict, dict) and candidate_dict.get("candidate"):
        logger.debug(f"Received ICE candidate for client {client_id}")
    else:
        logger.debug(f"Received non-standard ICE candidate format for client {client_id}")
    
    try:
        # Pass the candidate directly to the WebRTC manager
        result = await app_state.webrtc_manager.add_ice_candidate(client_id, candidate_dict)
        
        if result:
            logger.debug(f"Successfully added ICE candidate for client {client_id}")
        else:
            # Downgrade from warning to debug since this can be normal
            logger.debug(f"Could not add ICE candidate for client {client_id}")
            
    except Exception as e:
        logger.error(f"Error handling ICE candidate: {str(e)}")
        traceback.print_exc()

def parse_ice_candidate(candidate_str, candidate_dict):
    """Parse ICE candidate string into RTCIceCandidate object"""
    if not candidate_str:
        return None
        
    try:
        # The format is typically: candidate:foundation component protocol priority ip port type ...
        parts = candidate_str.split()
        
        if len(parts) >= 10 and parts[0].startswith("candidate:"):
            foundation = parts[0].split(":")[1]
            component = int(parts[1])
            protocol = parts[2]
            priority = int(parts[3])
            ip = parts[4]
            port = int(parts[5])
            candidate_type = parts[7]  # parts[6] should be "typ"
            
            return RTCIceCandidate(
                foundation=foundation,
                component=component,
                protocol=protocol,
                priority=priority,
                ip=ip,
                port=port,
                type=candidate_type,
                sdpMid=candidate_dict.get("sdpMid"),
                sdpMLineIndex=candidate_dict.get("sdpMLineIndex")
            )
    except Exception as e:
        logger.error(f"Error parsing ICE candidate: {str(e)}")
        
    return None