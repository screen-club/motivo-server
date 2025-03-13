import asyncio
import cv2
import json
import uuid
from typing import Dict, Set, Any, Tuple
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCConfiguration, RTCIceServer, RTCIceCandidate
from aiortc.contrib.media import MediaStreamTrack
import numpy as np
import fractions
import traceback
import logging
import time


logger = logging.getLogger('webrtc_manager')

class FrameVideoStreamTrack(VideoStreamTrack):
    """
    A video stream track that provides frames from the simulation.
    """

    def __init__(self, width=640, height=480, fps=30):
        super().__init__()
        self.latest_frame = None
        self.queue = asyncio.Queue(maxsize=1)
        self.frame_count = 0
        self.width = width
        self.height = height
        self.fps = fps
        self.time_base = fractions.Fraction(1, fps)
        self.frames_sent = 0
        logger.info(f"Created video track with resolution {width}x{height} @ {fps}fps")
        
    def update_frame(self, frame):
        """Update the latest frame to be sent to connected peers"""
        try:
            # If queue is full, clear it
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            # Process frame - make a copy to avoid modifying the original
            processed_frame = frame.copy()
            
            # NOTE: Frames should already be in RGB format from the simulation loop
            # env.render() returns RGB frames which are passed directly to this track
            
            # Resize frame to target resolution if needed with high-quality anti-aliasing
            if (processed_frame.shape[1] != self.width or 
                processed_frame.shape[0] != self.height):
                try:
                    # Use high-quality interpolation for resizing
                    processed_frame = cv2.resize(
                        processed_frame, 
                        (self.width, self.height), 
                        interpolation=cv2.INTER_LANCZOS4
                    )
                except Exception as e:
                    logger.error(f"Error resizing frame: {str(e)}")
                    # Fall back to a simpler method if LANCZOS fails
                    try:
                        processed_frame = cv2.resize(
                            processed_frame, 
                            (self.width, self.height), 
                            interpolation=cv2.INTER_AREA
                        )
                    except:
                        # Create a blank frame of the target size as a last resort
                        processed_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                
            # Successfully put frame in queue
            self.queue.put_nowait(processed_frame)
            self.frame_count += 1
            
        except Exception as e:
            logger.error(f"Error updating frame: {e}")
            traceback.print_exc()
    
    async def recv(self):
        """Get the latest frame to send to the client"""
        try:
            # Get frame with timeout
            try:
                frame = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except (asyncio.QueueEmpty, asyncio.TimeoutError):
                # Create a blank frame if no frame is available
                if hasattr(self, 'latest_frame') and self.latest_frame is not None:
                    frame = self.latest_frame
                    if self.frame_count % 30 == 0:  # Log every 30 frames (1 second at 30 fps)
                        logger.warning("Using previous frame - no new frame received")
                else:
                    frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    if self.frame_count % 30 == 0:  # Log every 30 frames
                        logger.warning("Sending blank frame - no frames available")
            
            # Store latest frame for backup
            self.latest_frame = frame
            self.frames_sent += 1
            
            # Create a VideoFrame from the numpy array
            from av import VideoFrame
            video_frame = VideoFrame.from_ndarray(frame, format='rgb24')
            
            # Set the timestamp based on the frame count and FPS
            pts = int(self.frame_count / self.fps * 90000)
            video_frame.pts = pts
            video_frame.time_base = self.time_base
            
            return video_frame
            
        except Exception as e:
            logger.error(f"Error in video track recv: {e}")
            traceback.print_exc()
            # Return an empty black frame as fallback
            try:
                # Create a completely new VideoFrame from scratch
                from av import VideoFrame
                blank_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                video_frame = VideoFrame.from_ndarray(blank_frame, format='rgb24')
                video_frame.pts = int(self.frame_count / self.fps * 90000)
                video_frame.time_base = self.time_base
                return video_frame
            except Exception as e2:
                logger.error(f"Critical error creating fallback frame: {e2}")
                raise  # Re-raise to let aiortc handle it

# Define the video quality configurations
VIDEO_CONFIGS = {
    "low": {"width": 640, "height": 360, "fps": 15},
    "medium": {"width": 960, "height": 540, "fps": 30},
    "high": {"width": 1280, "height": 720, "fps": 30},
    "hd": {"width": 1920, "height": 1080, "fps": 30}
}

class WebRTCManager:
    """
    Manages WebRTC connections and video streaming.
    """
    
    def __init__(self, video_quality="medium"):
        # ICE servers configuration - read from environment or use defaults
        import os
        
        # Get STUN/TURN server info from environment (or use default)
        stun_url = os.environ.get("VITE_STUN_URL", "stun:stun.l.google.com:19302")
        turn_url = os.environ.get("VITE_TURN_URL", "")
        turn_username = os.environ.get("VITE_TURN_USERNAME", "")
        turn_password = os.environ.get("VITE_TURN_PASSWORD", "")
        
        ice_servers = []
        
        # Add STUN server
        ice_servers.append(RTCIceServer(urls=[stun_url]))
        
        # Add TURN servers if configured
        if turn_url and turn_username and turn_password:
            # Regular TURN (UDP)
            ice_servers.append(
                RTCIceServer(
                    urls=[turn_url],
                    username=turn_username,
                    credential=turn_password
                )
            )
            
            # TURN over TCP (for restrictive firewalls)
            if turn_url.startswith("turn:"):
                tcp_turn_url = turn_url.replace("turn:", "turn:") + "?transport=tcp"
                ice_servers.append(
                    RTCIceServer(
                        urls=[tcp_turn_url],
                        username=turn_username,
                        credential=turn_password
                    )
                )
                
            # TURNS (TURN over TLS for secure connections)
            if turn_url.startswith("turn:"):
                turns_url = turn_url.replace("turn:", "turns:")
                ice_servers.append(
                    RTCIceServer(
                        urls=[turns_url],
                        username=turn_username,
                        credential=turn_password
                    )
                )
        
        logger.info(f"Configured with {len(ice_servers)} ICE servers")
        self.rtc_configuration = RTCConfiguration(ice_servers)
        
        # Store peer connections
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.tracks: Dict[str, FrameVideoStreamTrack] = {}
        
        # Set default video quality
        self.set_video_quality(video_quality)
        
        # Environment reference (set later)
        self.env = None
        
        logger.info(f"WebRTC manager initialized with {video_quality} quality")
    
    def set_environment(self, env):
        """Set the environment reference"""
        self.env = env
        logger.info("Environment set in WebRTC manager")
        
    def set_video_quality(self, quality_name):
        """Set the video quality for new connections"""
        if quality_name in VIDEO_CONFIGS:
            self.video_config = VIDEO_CONFIGS[quality_name]
            logger.info(f"Video quality set to {quality_name}: {self.video_config}")
        else:
            logger.warning(f"Unknown quality '{quality_name}', using medium")
            self.video_config = VIDEO_CONFIGS["medium"]
    
    async def create_peer_connection(self, client_id, offer):
        """Create a new peer connection for a client"""
        try:
            # Create a new peer connection
            pc = RTCPeerConnection(configuration=self.rtc_configuration)
            
            # Register callback handlers
            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logger.info(f"ICE Connection state for {client_id}: {pc.iceConnectionState}")
                if pc.iceConnectionState == "failed" or pc.iceConnectionState == "closed":
                    await self.close_connection(client_id)
            
            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.info(f"Connection state for {client_id}: {pc.connectionState}")
                if pc.connectionState == "failed" or pc.connectionState == "closed":
                    await self.close_connection(client_id)
            
            # Create a video track with the current quality settings
            track = FrameVideoStreamTrack(
                width=self.video_config["width"],
                height=self.video_config["height"],
                fps=self.video_config["fps"]
            )
            
            # Add track to peer connection
            pc.addTrack(track)
            
            # Process the offer
            offer_obj = RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
            await pc.setRemoteDescription(offer_obj)
            
            # Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            # Store the connection and track
            self.peer_connections[client_id] = pc
            self.tracks[client_id] = track
            
            logger.info(f"Created peer connection for client {client_id}")
            
            # Return the answer
            return {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }
            
        except Exception as e:
            logger.error(f"Error creating peer connection: {e}")
            traceback.print_exc()
            return None
    
    async def add_ice_candidate(self, client_id, candidate):
        """Add an ICE candidate to a peer connection"""
        try:
            if client_id in self.peer_connections:
                pc = self.peer_connections[client_id]
                candidate_obj = RTCIceCandidate(
                    component=candidate.get("component", 0),
                    foundation=candidate.get("foundation", ""),
                    ip=candidate.get("ip", ""),
                    port=candidate.get("port", 0),
                    priority=candidate.get("priority", 0),
                    protocol=candidate.get("protocol", ""),
                    type=candidate.get("type", ""),
                    sdpMid=candidate.get("sdpMid", ""),
                    sdpMLineIndex=candidate.get("sdpMLineIndex", 0)
                )
                await pc.addIceCandidate(candidate_obj)
                logger.debug(f"Added ICE candidate for client {client_id}")
                return True
            else:
                logger.warning(f"No peer connection found for client {client_id} to add ICE candidate")
                return False
        except Exception as e:
            logger.error(f"Error adding ICE candidate: {e}")
            traceback.print_exc()
            return False
    
    async def broadcast_frame(self, frame):
        """Send a frame to all connected peers"""
        if not self.tracks:
            return 0  # No connected peers
        
        try:
            # Check if frame is valid
            if frame is None or frame.size == 0:
                logger.warning("Received empty frame for broadcast")
                # Create a blank frame as fallback
                frame = np.zeros((480, 640, 3), dtype=np.uint8)

            # Log frame stats occasionally for debugging
            if hasattr(self, '_frame_count'):
                self._frame_count += 1
            else:
                self._frame_count = 0
                
            if self._frame_count % 100 == 0:
                logger.debug(f"Display frame before conversion: shape={frame.shape}, dtype={frame.dtype}, min={frame.min()}, max={frame.max()}")
                
            # In the refactored code, frames are already in RGB format from env.render()
            # So we don't need to convert BGR to RGB anymore
            frame_rgb = frame.copy()
            
            # Only log on occasional frames for debugging
            if self._frame_count % 500 == 0:
                logger.debug(f"Using RGB frame directly: shape={frame.shape}, dtype={frame.dtype}, min={frame.min()}, max={frame.max()}")
            
            # Update all tracks with the new frame
            update_count = 0
            for client_id, track in self.tracks.items():
                try:
                    track.update_frame(frame_rgb.copy())  # Use a copy to avoid issues with concurrent modification
                    update_count += 1
                except Exception as e:
                    logger.error(f"Error updating track for client {client_id}: {e}")
            
            return update_count  # Return number of successful updates
        except Exception as e:
            logger.error(f"Error broadcasting frame: {e}")
            traceback.print_exc()
            return 0
    
    async def close_connection(self, client_id):
        """Close a specific peer connection"""
        try:
            if client_id in self.peer_connections:
                pc = self.peer_connections[client_id]
                logger.info(f"Closing connection for client {client_id}")
                
                # Close the peer connection
                await pc.close()
                
                # Remove from dictionaries
                del self.peer_connections[client_id]
                
                if client_id in self.tracks:
                    del self.tracks[client_id]
                
                logger.info(f"Connection closed for client {client_id}")
                return True
            else:
                logger.warning(f"No connection found for client {client_id}")
                return False
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
            traceback.print_exc()
            return False
    
    async def close_all_connections(self):
        """Close all peer connections"""
        logger.info(f"Closing all {len(self.peer_connections)} WebRTC connections")
        
        # Get a list of client IDs to avoid modifying dict during iteration
        client_ids = list(self.peer_connections.keys())
        
        # Close each connection
        for client_id in client_ids:
            await self.close_connection(client_id)
        
        logger.info("All WebRTC connections closed")
        
    def get_connection_stats(self):
        """Get statistics about current connections"""
        return {
            "connections": len(self.peer_connections),
            "active_tracks": len(self.tracks),
            "video_config": self.video_config
        }