import asyncio
import logging
import os
import time
from typing import Dict, Optional, List

import av
import cv2
import numpy as np
import fractions
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer, RTCIceCandidate
from aiortc.contrib.media import MediaStreamTrack, MediaRelay, MediaPlayer, MediaRecorder
from aiortc.mediastreams import VideoStreamTrack

logger = logging.getLogger('webrtc_manager')

# Video quality configurations
VIDEO_CONFIGS = {
    "low": {"width": 640, "height": 360, "fps": 15},
    "medium": {"width": 960, "height": 540, "fps": 30},
    "high": {"width": 1280, "height": 720, "fps": 30},
    "hd": {"width": 1920, "height": 1080, "fps": 30}
}

class FrameTransformer:
    """
    Transform frames before sending them over WebRTC.
    Uses OpenCV for efficient image processing and maintains aspect ratio.
    """
    def __init__(self, width=640, height=480):
        self.width = width
        self.height = height
        self.last_frame = None
        
    def transform(self, frame):
        """Process a frame for sending over WebRTC with aspect ratio preservation"""
        try:
            # Make a copy to avoid modifying original
            result = frame.copy()
            
            # Check dimensions
            if result.shape[1] != self.width or result.shape[0] != self.height:
                # Calculate aspect ratio
                src_aspect = result.shape[1] / result.shape[0]  # width / height
                dst_aspect = self.width / self.height
                
                # Resize differently based on aspect ratio
                if src_aspect != dst_aspect:
                    logger.debug(f"Input frame has different aspect ratio: {src_aspect:.2f} vs target {dst_aspect:.2f}")
                    
                    # Create a black canvas of target size
                    canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    
                    if src_aspect > dst_aspect:
                        # Source is wider, scale to target width and center vertically
                        new_height = int(self.width / src_aspect)
                        scaled = cv2.resize(
                            result, 
                            (self.width, new_height),
                            interpolation=cv2.INTER_AREA
                        )
                        # Calculate vertical offset to center
                        y_offset = (self.height - new_height) // 2
                        # Place on canvas
                        canvas[y_offset:y_offset+new_height, 0:self.width] = scaled
                    else:
                        # Source is taller, scale to target height and center horizontally
                        new_width = int(self.height * src_aspect)
                        scaled = cv2.resize(
                            result, 
                            (new_width, self.height),
                            interpolation=cv2.INTER_AREA
                        )
                        # Calculate horizontal offset to center
                        x_offset = (self.width - new_width) // 2
                        # Place on canvas
                        canvas[0:self.height, x_offset:x_offset+new_width] = scaled
                    
                    result = canvas
                else:
                    # Aspect ratios match, do a simple resize
                    result = cv2.resize(
                        result, 
                        (self.width, self.height),
                        interpolation=cv2.INTER_AREA
                    )
                
            # Store last successfully processed frame
            self.last_frame = result
            return result
            
        except Exception as e:
            logger.error(f"Frame transform error: {e}")
            
            # Return last good frame or create blank frame
            if self.last_frame is not None:
                return self.last_frame
            else:
                return np.zeros((self.height, self.width, 3), dtype=np.uint8)

class FrameVideoStreamTrack(VideoStreamTrack):
    """
    A simplified video stream track that sends frames from the simulation.
    Uses aiortc's built-in VideoStreamTrack.
    """
    def __init__(self, width=640, height=480, fps=30):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_transformer = FrameTransformer(width, height)
        self.frame_queue = asyncio.Queue(maxsize=1)
        self.counter = 0
        self.start_time = time.time()
        # Use fractions for time_base (standard in aiortc)
        self.time_base = fractions.Fraction(1, 90000)
        
    def update_frame(self, frame):
        """Update the frame to be sent to connected peers"""
        try:
            # Transform the frame
            processed_frame = self.frame_transformer.transform(frame)
            
            # Add to queue, replacing older frame if necessary
            try:
                self.frame_queue.put_nowait(processed_frame)
            except asyncio.QueueFull:
                # Empty the queue and add new frame
                try:
                    _ = self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(processed_frame)
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"Error updating frame: {e}")
            
    async def recv(self):
        """Get the next frame to send"""
        try:
            # Get frame with timeout
            try:
                frame = await asyncio.wait_for(self.frame_queue.get(), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.QueueEmpty):
                # Use last transformed frame or create blank frame
                frame = self.frame_transformer.last_frame
                if frame is None:
                    frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    
            # Convert to VideoFrame
            pts = int((time.time() - self.start_time) * 90000)
            video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
            video_frame.pts = pts
            # Use self.time_base instead of av.Rational
            video_frame.time_base = self.time_base
            
            self.counter += 1
            return video_frame
            
        except Exception as e:
            logger.error(f"Error in recv: {e}")
            # Create blank frame as fallback
            pts = int((time.time() - self.start_time) * 90000)
            blank_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            video_frame = av.VideoFrame.from_ndarray(blank_frame, format="rgb24")
            video_frame.pts = pts
            video_frame.time_base = self.time_base
            return video_frame

class WebRTCManager:
    """
    Simplified WebRTC manager using aiortc library.
    """
    def __init__(self, video_quality="medium"):
        # Configure ICE servers
        self.ice_servers = self._configure_ice_servers()
        
        # Create RTCConfiguration
        self.rtc_configuration = RTCConfiguration(iceServers=self.ice_servers)
        
        # Media relay for efficient stream sharing
        self.relay = MediaRelay()
        
        # Set video quality
        self.set_video_quality(video_quality)
        
        # Track connections
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.tracks: Dict[str, FrameVideoStreamTrack] = {}
        
        # Stats
        self.stats = {
            "created_connections": 0,
            "active_connections": 0,
            "closed_connections": 0
        }
        
        # Environment reference (set later)
        self.env = None
        
        logger.info(f"WebRTC manager initialized with {video_quality} quality")
        
    def _configure_ice_servers(self) -> List[RTCIceServer]:
        """Configure ICE servers based on environment variables"""
        use_ice = os.environ.get('USE_ICE_SERVER', 'true').lower() != 'false'
        if not use_ice:
            logger.info("Skipping external ICE servers")
            return []
            
        logger.info("Configuring ICE servers for WebRTC")
        ice_servers = []
        
        # Add STUN servers
        stun_urls = [
            "stun:stun.l.google.com:19302",
            "stun:stun1.l.google.com:19302"
        ]
        
        # Add custom STUN server if provided
        custom_stun = os.environ.get("VITE_STUN_URL")
        if custom_stun:
            stun_urls.insert(0, custom_stun)
            
        ice_servers.append(RTCIceServer(urls=stun_urls))
        
        # Add TURN server if configured
        turn_url = os.environ.get("VITE_TURN_URL")
        turn_username = os.environ.get("VITE_TURN_USERNAME") 
        turn_password = os.environ.get("VITE_TURN_PASSWORD")
        
        if turn_url and turn_username and turn_password:
            # Add UDP TURN server
            ice_servers.append(RTCIceServer(
                urls=[turn_url],
                username=turn_username,
                credential=turn_password
            ))
            
            # Add TCP TURN server
            if turn_url.startswith("turn:"):
                ice_servers.append(RTCIceServer(
                    urls=[f"{turn_url}?transport=tcp"],
                    username=turn_username,
                    credential=turn_password
                ))
                
        logger.info(f"Configured {len(ice_servers)} ICE servers")
        return ice_servers
        
    def set_environment(self, env):
        """Set the environment reference"""
        self.env = env
        logger.info("Environment set in WebRTC manager")
        
    def set_video_quality(self, quality_name):
        """Set the video quality for new connections"""
        if quality_name in VIDEO_CONFIGS:
            self.video_config = VIDEO_CONFIGS[quality_name]
            logger.info(f"Video quality set to {quality_name}: {self.video_config}")
            return True
        else:
            logger.warning(f"Unknown quality '{quality_name}', using medium")
            self.video_config = VIDEO_CONFIGS["medium"]
            return False
            
    async def create_peer_connection(self, client_id, offer):
        """Create a peer connection for a client"""
        try:
            # Close any existing connection first
            if client_id in self.peer_connections:
                logger.info(f"Closing existing connection for {client_id}")
                await self.close_connection(client_id)
                
            # Create new peer connection
            pc = RTCPeerConnection(configuration=self.rtc_configuration)
            logger.info(f"Created peer connection for {client_id}")
            
            # Event handlers
            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.info(f"Connection state changed to {pc.connectionState} for {client_id}")
                if pc.connectionState == "failed" or pc.connectionState == "closed":
                    await self.close_connection(client_id)
                    
            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logger.info(f"ICE connection state changed to {pc.iceConnectionState} for {client_id}")
                
            # Create video track
            track = FrameVideoStreamTrack(
                width=self.video_config["width"],
                height=self.video_config["height"],
                fps=self.video_config["fps"]
            )
            
            # Add track to peer connection
            pc.addTrack(track)
            
            # Set remote description
            await pc.setRemoteDescription(RTCSessionDescription(
                sdp=offer["sdp"],
                type=offer["type"]
            ))
            
            # Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            # Store connection and track
            self.peer_connections[client_id] = pc
            self.tracks[client_id] = track
            
            # Update stats
            self.stats["created_connections"] += 1
            self.stats["active_connections"] = len(self.peer_connections)
            
            # Return the answer
            return {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }
            
        except Exception as e:
            logger.error(f"Error creating peer connection: {e}")
            return None
            
    async def add_ice_candidate(self, client_id, candidate_dict):
        """Add an ICE candidate to a peer connection"""
        try:
            # Check for valid inputs
            if not candidate_dict or client_id not in self.peer_connections:
                return False
                
            pc = self.peer_connections[client_id]
            
            # Extract candidate info
            candidate = candidate_dict.get("candidate", "")
            sdpMid = candidate_dict.get("sdpMid")
            sdpMLineIndex = candidate_dict.get("sdpMLineIndex")
            
            if not candidate:
                # Empty candidate - normal for end-of-candidates
                return True
                
            # Create candidate object
            ice_candidate = RTCIceCandidate(
                candidate=candidate,
                sdpMid=sdpMid,
                sdpMLineIndex=sdpMLineIndex
            )
            
            # Add to peer connection
            await pc.addIceCandidate(ice_candidate)
            return True
            
        except Exception as e:
            logger.error(f"Error adding ICE candidate: {e}")
            return False
            
    async def broadcast_frame(self, frame):
        """Send a frame to all connected peers"""
        if not self.tracks:
            return 0
            
        try:
            if frame is None:
                # Skip empty frames
                return 0
                
            # Update all tracks
            updated = 0
            for client_id, track in list(self.tracks.items()):
                try:
                    # Verify connection is still active
                    if client_id in self.peer_connections:
                        pc = self.peer_connections[client_id]
                        if pc.connectionState != "closed" and pc.connectionState != "failed":
                            track.update_frame(frame)
                            updated += 1
                except Exception as e:
                    logger.error(f"Error updating track for {client_id}: {e}")
                    
            return updated
            
        except Exception as e:
            logger.error(f"Error broadcasting frame: {e}")
            return 0
            
    async def close_connection(self, client_id):
        """Close a peer connection"""
        try:
            if client_id not in self.peer_connections:
                return False
                
            pc = self.peer_connections[client_id]
            logger.info(f"Closing connection for {client_id}")
            
            # Close peer connection
            await pc.close()
            
            # Remove from tracking
            if client_id in self.tracks:
                del self.tracks[client_id]
                
            if client_id in self.peer_connections:
                del self.peer_connections[client_id]
                
            # Update stats
            self.stats["active_connections"] = len(self.peer_connections)
            self.stats["closed_connections"] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
            
            # Force cleanup
            if client_id in self.tracks:
                del self.tracks[client_id]
            if client_id in self.peer_connections:
                del self.peer_connections[client_id]
                
            return False
            
    async def close_all_connections(self):
        """Close all peer connections"""
        client_ids = list(self.peer_connections.keys())
        for client_id in client_ids:
            await self.close_connection(client_id)
            
        logger.info("All WebRTC connections closed")
        
    def get_connection_stats(self):
        """Get statistics about connections"""
        self.stats["active_connections"] = len(self.peer_connections)
        
        # Collect connection states
        states = {}
        for client_id, pc in self.peer_connections.items():
            state = pc.connectionState
            if state not in states:
                states[state] = 0
            states[state] += 1
            
        return {
            "connections": self.stats["active_connections"],
            "created_total": self.stats["created_connections"],
            "closed_total": self.stats["closed_connections"],
            "states": states,
            "video_config": self.video_config,
            "timestamp": time.time()
        }