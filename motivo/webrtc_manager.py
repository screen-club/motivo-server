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
            
            # NOTE: We don't convert color here anymore
            # The WebRTCManager class already converted BGR to RGB
            
            # Resize frame to target resolution if needed with high-quality anti-aliasing
            if processed_frame.shape[1] != self.width or processed_frame.shape[0] != self.height:
                try:
                    # Use high-quality interpolation for resizing
                    processed_frame = cv2.resize(
                        processed_frame, 
                        (self.width, self.height), 
                        interpolation=cv2.INTER_LANCZOS4
                    )
                except Exception as e:
                    logger.error(f"Error resizing frame: {str(e)}")
                    # Create a blank frame of the target size as a fallback
                    processed_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            
            # Log frame stats occasionally (every 100 frames)
            #if self.frame_count % 100 == 0:
                #logger.info(f"Frame stats: shape={processed_frame.shape}, min={processed_frame.min()}, max={processed_frame.max()}")
            
            # Put new frame in queue
            self.queue.put_nowait(processed_frame)
        except Exception as e:
            logger.error(f"Error updating frame: {str(e)}")
            # If all else fails, try to put an empty frame in the queue
            try:
                blank_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                self.queue.put_nowait(blank_frame)
            except:
                pass

    async def recv(self):
        """Return a new video frame."""
        self.frame_count += 1
        pts, time_base = self.frame_count, self.time_base
        
        # Get the latest frame from the queue
        try:
            # Wait for a frame with timeout
            frame = await asyncio.wait_for(self.queue.get(), timeout=1.0)
        except (asyncio.QueueEmpty, asyncio.TimeoutError):
            # Create a blank frame if no frame is available
            if self.latest_frame is not None:
                frame = self.latest_frame
                if self.frame_count % 30 == 0:  # Log every 30 frames (1 second at 30 fps)
                    logger.warning("Using previous frame - no new frame received")
            else:
                frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                if self.frame_count % 30 == 0:  # Log every 30 frames
                    logger.warning("Sending blank frame - no frames available")
        
        # Store latest frame
        self.latest_frame = frame
        
        # The frame is already in RGB format (converted in update_frame method)
        # No need for additional conversion
        rgb_frame = frame
        
        # Create a VideoFrame from the numpy array with high quality settings
        from av import VideoFrame
        video_frame = VideoFrame.from_ndarray(rgb_frame, format='rgb24')
        
        # Set quality-related parameters
        video_frame.pts = pts
        video_frame.time_base = time_base
        
        # Count successful frames sent
        self.frames_sent += 1
       
            
        return video_frame

class WebRTCManager:
    """
    Manages WebRTC peer connections for video streaming.
    """
    def __init__(self, video_quality="medium", env=None):
        # Video quality presets
        self.quality_presets = {
            "medium": (640, 480, 30),    # Width, Height, FPS
            "high": (1280, 960, 30)      # Width, Height, FPS
        }
        
        # Store reference to environment if provided
        self.env = env
        
        # Encoder settings - simplified for clean output
        self.encoder_settings = {
            "medium": {
                "preset": "medium",       # Balanced preset
                "tune": None,             # No specific tuning
                "crf": 18,                # Lower CRF = higher quality (was 20)
                "profile": "main"
            },
            "high": {
                "preset": "medium",       # Balanced preset (was "slow")
                "tune": None,             # No specific tuning
                "crf": 18,                # Same quality level for consistency
                "profile": "high"
            }
        }
        
        # Select quality preset
        width, height, fps = self.quality_presets.get(video_quality, self.quality_presets["medium"])
        
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.video_track = FrameVideoStreamTrack(width=width, height=height, fps=fps)
        self.video_quality = video_quality
        
        # Configure codec options based on quality - simpler configuration
        self.codec_options = {
            "video_codecs": ["H264", "VP9", "VP8"],
            "encoder_settings": self.encoder_settings[video_quality]
        }
        
        # Set initial environment render resolution if environment is available
        if self.env is not None:
            self.set_environment_resolution(width, height)
    
    def set_environment_resolution(self, width, height):
        """
        Update the environment's render resolution if possible
        """
        if self.env is None:
            print("Environment not available, can't set render resolution")
            return False
            
        try:
            # Different environments may have different ways to set the resolution
            # Try to handle the common cases
            
            # Method 1: If the environment has a set_render_resolution method
            if hasattr(self.env, 'set_render_resolution'):
                self.env.set_render_resolution(width=width, height=height)
                print(f"Set environment render resolution to {width}x{height}")
                return True
                
            # Method 2: If the environment has render_width and render_height attributes
            elif hasattr(self.env, 'render_width') and hasattr(self.env, 'render_height'):
                self.env.render_width = width
                self.env.render_height = height
                print(f"Set environment render resolution to {width}x{height} via attributes")
                return True
                
            # Method 3: Try to access the unwrapped environment
            elif hasattr(self.env, 'unwrapped'):
                unwrapped_env = self.env.unwrapped
                
                # Some environments use camera configs
                if hasattr(unwrapped_env, 'camera_config'):
                    if 'render_resolution' in unwrapped_env.camera_config:
                        unwrapped_env.camera_config['render_resolution'] = (width, height)
                        print(f"Set environment render resolution to {width}x{height} via camera_config")
                        return True
                
                # For MuJoCo environments
                if hasattr(unwrapped_env, 'model') and hasattr(unwrapped_env, 'sim'):
                    # This is a best effort for MuJoCo environments
                    # Different versions might handle this differently
                    try:
                        from mujoco import MjRenderContext
                        # If this is a MuJoCo environment, we can try to set the resolution
                        # through the render context
                        if hasattr(unwrapped_env, 'render_context'):
                            unwrapped_env.render_context.render_resolution = (width, height)
                            print(f"Set MuJoCo render resolution to {width}x{height}")
                            return True
                    except (ImportError, AttributeError):
                        pass
            
            print("Could not find a way to set the environment render resolution")
            return False
            
        except Exception as e:
            print(f"Error setting environment resolution: {str(e)}")
            return False
    
    def set_environment(self, env):
        """
        Set or update the environment reference and apply current resolution
        """
        self.env = env
        if self.env is not None:
            width, height, _ = self.quality_presets.get(self.video_quality, self.quality_presets["medium"])
            return self.set_environment_resolution(width, height)
        return False
    
    def update_frame(self, frame):
        """
        Updates the current frame to be streamed to all peers.
        The input frame is now in BGR format (from DisplayManager).
        """
        try:
            # Check if frame is None and create a black frame as fallback
            if frame is None:
                logger.warning("Received None frame from environment, generating blank frame")
                blank_frame = np.zeros((self.video_track.height, self.video_track.width, 3), dtype=np.uint8)
                
                # Add text to indicate no frame is available
                cv2.putText(
                    blank_frame,
                    "No frame available",
                    (self.video_track.width // 4, self.video_track.height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA
                )
                
                # Convert to RGB (WebRTC expects RGB)
                if blank_frame.shape[2] == 3:
                    blank_frame = cv2.cvtColor(blank_frame, cv2.COLOR_BGR2RGB)
                    
                self.video_track.update_frame(blank_frame)
                return
            
            # Make a copy to avoid modifying the original
            processed_frame = frame.copy()
            
            # Check for black/empty frames
            if processed_frame.mean() < 5:  # Very dark frame
                logger.warning("Received nearly black frame from environment")
            
            # Convert from BGR (from DisplayManager) back to RGB for WebRTC
            if processed_frame.shape[2] == 3:
                processed_frame = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
            
            # Update the video track with the RGB frame
            self.video_track.update_frame(processed_frame)
        except Exception as e:
            logger.error(f"Error updating frame: {str(e)}")
            # If update fails, try to send an empty frame
            try:
                blank_frame = np.zeros((self.video_track.height, self.video_track.width, 3), dtype=np.uint8)
                self.video_track.update_frame(blank_frame)
            except:
                logger.error(f"Failed to send blank frame after error")
                pass
    
    def set_video_quality(self, quality):
        """
        Change the video quality preset.
        """
        if quality in self.quality_presets:
            width, height, fps = self.quality_presets[quality]
            
            # Set environment resolution first if available
            if self.env is not None:
                self.set_environment_resolution(width, height)
            
            # Create a new video track with the new quality settings
            old_track = self.video_track
            self.video_track = FrameVideoStreamTrack(width=width, height=height, fps=fps)
            self.video_quality = quality
            
            # Update codec options
            self.codec_options["encoder_settings"] = self.encoder_settings[quality]
            
            # Update all existing connections with the new track
            for client_id, pc in self.peer_connections.items():
                # Find the old sender
                senders = pc.getTransceivers()
                for sender in senders:
                    if sender.sender and sender.sender.track == old_track:
                        # Replace the track
                        sender.sender.replaceTrack(self.video_track)
            
            print(f"Changed video quality to {quality}: {width}x{height} @ {fps}fps")
            return True
        return False
    
    async def create_peer_connection(self, client_id=None):
        """
        Create a new peer connection for a client.
        """
        if client_id is None:
            client_id = str(uuid.uuid4())
            
        # Create RTCPeerConnection with explicit configuration for Docker environments
        # Add STUN and TURN servers for better connectivity in Docker
        ice_servers = []
        
        # Get COTURN configuration from environment variables
        import os
        
        stun_url = os.getenv("VITE_STUN_URL")
        turn_url = os.getenv("VITE_TURN_URL")
        turn_username = os.getenv("VITE_TURN_USERNAME")
        turn_password = os.getenv("VITE_TURN_PASSWORD")
        
        # Enhanced debugging for environment variables
        logger.info(f"WebRTC Config - STUN URL: {stun_url or 'Not set'}")
        logger.info(f"WebRTC Config - TURN URL: {turn_url or 'Not set'}")
        logger.info(f"WebRTC Config - TURN Username: {'Set' if turn_username else 'Not set'}")
        logger.info(f"WebRTC Config - TURN Password: {'Set' if turn_password else 'Not set'}")
        
        # Add STUN server if configured
        if stun_url:
            ice_servers.append(RTCIceServer(urls=[stun_url]))
        else:
            # Fallback to Google's public STUN servers if not configured
            logger.warning("No STUN server configured, using Google's public STUN servers as fallback")
            ice_servers.append(RTCIceServer(urls=["stun:stun.l.google.com:19302"]))
        
        # Add TURN server if configured
        if turn_url and turn_username and turn_password:
            # Standard TURN over UDP
            ice_servers.append(RTCIceServer(
                urls=[turn_url],
                username=turn_username,
                credential=turn_password
            ))
            
            # TURN over TCP for firewall traversal
            ice_servers.append(RTCIceServer(
                urls=[f"{turn_url}?transport=tcp"],
                username=turn_username,
                credential=turn_password
            ))
            
            # TURNS (TURN over TLS) for secure connections
            turns_url = turn_url.replace("turn:", "turns:").replace("3478", "5349")
            ice_servers.append(RTCIceServer(
                urls=[turns_url],
                username=turn_username,
                credential=turn_password
            ))
        else:
            logger.warning("No TURN server configuration found. WebRTC may fail in restricted network environments.")
        
        logger.info(f"Creating peer connection for {client_id} with {len(ice_servers)} ICE servers")
        
        # Create RTCConfiguration with ice servers
        config = RTCConfiguration(iceServers=ice_servers)
        pc = RTCPeerConnection(config)
        
        self.peer_connections[client_id] = pc
        
        # Add the video track with codec preferences
        sender = pc.addTrack(self.video_track)
        
        # Try to configure encoder parameters for better raw quality
        try:
            # Set encoding parameters for H.264 and VP8/VP9
            if hasattr(sender, 'setParameters'):
                params = sender.getParameters()
                if hasattr(params, 'encodings') and params.encodings:
                    # Set bitrate - high enough for clean video but not excessive
                    if self.video_quality == "medium":
                        max_bitrate = 3_000_000  # 3Mbps (was 2.5Mbps)
                    elif self.video_quality == "high":
                        max_bitrate = 6_000_000  # 6Mbps (was 5Mbps)
                    
                    # Apply bitrate limit
                    for encoding in params.encodings:
                        encoding.maxBitrate = max_bitrate
                        encoding.maxFramerate = self.video_track.fps
                        # Use "very-high" priority
                        encoding.priority = "very-high"
                        # Disable any enhancements
                        if hasattr(encoding, 'scaleResolutionDownBy'):
                            encoding.scaleResolutionDownBy = 1.0  # No downscaling
                        if hasattr(encoding, 'active'):
                            encoding.active = True
                    
                    # Apply the parameters
                    sender.setParameters(params)
                    logger.info(f"Set max bitrate to {max_bitrate/1_000_000}Mbps for {client_id}")
        except Exception as e:
            logger.error(f"Error setting encoding parameters: {str(e)}")
        
        # Add extra logging for ICE gathering
        pc.on("icegatheringstatechange", lambda: logger.info(
            f"ICE gathering state changed for {client_id}: {pc.iceGatheringState}")
        )
        
        # Enhanced ICE candidate logging with full details
        @pc.on("icecandidate")
        def on_icecandidate(candidate):
            if candidate:
                # Log detailed candidate information
                logger.info(
                    f"ICE candidate for {client_id}: {candidate.type} {candidate.protocol} "
                    f"{candidate.ip}:{candidate.port} {candidate.component}"
                )
                
                # Save statistics about candidate types
                if not hasattr(pc, '_candidate_stats'):
                    pc._candidate_stats = {'host': 0, 'srflx': 0, 'prflx': 0, 'relay': 0}
                
                if candidate.type:
                    pc._candidate_stats[candidate.type] += 1
                    
                    # Log a summary of gathered candidates periodically
                    logger.info(f"Candidate stats for {client_id}: {pc._candidate_stats}")
            else:
                # ICE gathering is complete when candidate is None
                logger.info(f"ICE gathering completed for {client_id}")
                if hasattr(pc, '_candidate_stats'):
                    logger.info(f"Final candidate stats for {client_id}: {pc._candidate_stats}")
                else:
                    logger.warning(f"No ICE candidates gathered for {client_id}")
        
        # Handle ICE connection state changes
        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.info(f"ICE connection state for {client_id}: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed" or pc.iceConnectionState == "closed":
                # Use a safe closure method to prevent KeyErrors
                await self.safe_close_peer_connection(client_id)
        
        # Handle connection state changes
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state for {client_id}: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                # Use a safe closure method to prevent KeyErrors
                await self.safe_close_peer_connection(client_id)
        
        return pc, client_id
    
    async def handle_offer(self, client_id, sdp):
        """
        Handle a WebRTC offer from a client.
        """
        logger.info(f"Received WebRTC offer from client {client_id}")
        
        try:
            # Validate SDP content before processing
            if not sdp or len(sdp) < 50:  # Basic validation check
                logger.error(f"Invalid SDP received from client {client_id}: {sdp[:100]}")
                return {"sdp": "", "type": "failed", "error": "Invalid SDP format"}
                
            # Check if we already have an existing connection that might be stale
            if client_id in self.peer_connections:
                pc = self.peer_connections[client_id]
                # Check connection state more thoroughly
                if pc.connectionState in ["failed", "closed", "disconnected"] or pc.iceConnectionState in ["failed", "closed", "disconnected"]:
                    logger.info(f"Replacing stale peer connection for client {client_id}")
                    # Close old connection safely first
                    await self.safe_close_peer_connection(client_id)
                    # Then create a new one
                    pc, _ = await self.create_peer_connection(client_id)
                else:
                    logger.info(f"Using existing peer connection for client {client_id}")
                    
                    # Double-check if the connection is actually usable
                    # This helps prevent "RTCPeerConnection is closed" errors
                    if hasattr(pc, '_isClosed') and pc._isClosed:
                        logger.info(f"Connection marked as closed internally, creating new connection for {client_id}")
                        await self.safe_close_peer_connection(client_id)
                        pc, _ = await self.create_peer_connection(client_id)
            else:
                logger.info(f"Creating new peer connection for client {client_id}")
                pc, _ = await self.create_peer_connection(client_id)
            
            # Set the remote description
            offer = RTCSessionDescription(sdp=sdp, type="offer")
            try:
                await pc.setRemoteDescription(offer)
                logger.info(f"Set remote description for client {client_id}")
            except Exception as e:
                logger.error(f"Error setting remote description: {str(e)}")
                raise
            
            # Create an answer
            try:
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                logger.info(f"Created answer for client {client_id}: {answer.type}")
                
                # Log ICE candidates for debugging
                logger.info(f"Local ICE candidates for {client_id}: {len(pc.localDescription.sdp.split('a=candidate:'))}")
                
                # Log SDP details for diagnostic purposes
                sdp_lines = pc.localDescription.sdp.split('\n')
                media_lines = [line for line in sdp_lines if line.startswith('m=')]
                codec_lines = [line for line in sdp_lines if line.startswith('a=rtpmap:')]
                logger.info(f"SDP Media sections: {media_lines}")
                logger.info(f"SDP Codecs: {codec_lines[:5]}")  # Log first 5 codecs
                
                return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
            except Exception as e:
                # If answer creation fails, it might be due to invalid state
                logger.error(f"Error creating answer: {str(e)}")
                if "is closed" in str(e):
                    # Connection is closed, create a new one and try again
                    logger.info(f"Connection was closed, creating new connection for {client_id}")
                    await self.safe_close_peer_connection(client_id)
                    pc, _ = await self.create_peer_connection(client_id)
                    
                    # Try again with the new connection
                    offer = RTCSessionDescription(sdp=sdp, type="offer")
                    await pc.setRemoteDescription(offer)
                    answer = await pc.createAnswer()
                    await pc.setLocalDescription(answer)
                    logger.info(f"Created answer with new connection for {client_id}: {answer.type}")
                    
                    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
                else:
                    # Rethrow other errors
                    raise
        except Exception as e:
            logger.error(f"Error handling WebRTC offer: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Clean up after error
            try:
                await self.safe_close_peer_connection(client_id)
            except Exception:
                pass
            
            # Return a failure response so client can retry
            return {
                "sdp": "",
                "type": "failed",
                "error": str(e)
            }
    
    async def safe_close_peer_connection(self, client_id):
        """
        Safely close a peer connection with proper error handling
        """
        if client_id in self.peer_connections:
            pc = self.peer_connections[client_id]
            try:
                logger.info(f"Safely closing peer connection for client {client_id}")
                
                # Before closing the connection, cancel any pending ICE transactions
                # This helps prevent "NoneType has no attribute sendto" errors
                try:
                    # Get all transceivers and cancel their pending operations
                    transceivers = pc.getTransceivers()
                    for transceiver in transceivers:
                        # If transceiver has a sender with an active track, stop it
                        if transceiver.sender and transceiver.sender.track:
                            transceiver.sender.track.stop()
                except Exception as e:
                    logger.error(f"Error stopping tracks: {str(e)}")
                
                # Create a separate task to close the connection with a timeout
                # This prevents blocking the main execution while waiting for close
                try:
                    # Set a timeout for the close operation
                    close_task = asyncio.create_task(self.close_peer_connection(client_id))
                    await asyncio.wait_for(close_task, timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout while closing connection for {client_id}")
                except Exception as e:
                    logger.error(f"Error in close task: {str(e)}")
                    
            except Exception as e:
                logger.error(f"Error during safe connection close: {str(e)}")
                traceback.print_exc()
            finally:
                # Make sure connection is removed from our tracking
                if client_id in self.peer_connections:
                    del self.peer_connections[client_id]
                if client_id in self.data_channels:
                    del self.data_channels[client_id]
                if client_id in self.connection_timestamps:
                    del self.connection_timestamps[client_id]
                    
                logger.info(f"Peer connection for client {client_id} has been removed")
                
                # Force a garbage collection to free up resources
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
                    
        return True
    
    async def close_peer_connection(self, client_id):
        """
        Close a peer connection properly
        """
        if client_id in self.peer_connections:
            pc = self.peer_connections[client_id]
            try:
                # Set all senders' tracks to null before closing
                for sender in pc.getSenders():
                    if sender.track:
                        sender.replaceTrack(None)
                
                # Close the connection with a proper state transition
                logger.info(f"Closing peer connection for client {client_id}")
                await pc.close()
                logger.info(f"Peer connection closed for {client_id}")
            except Exception as e:
                logger.error(f"Error closing peer connection: {str(e)}")
    
    async def close_all_connections(self):
        """
        Close all peer connections.
        """
        # Make a copy of the keys to avoid modification during iteration
        client_ids = list(self.peer_connections.keys())
        for client_id in client_ids:
            await self.safe_close_peer_connection(client_id)
    
    def get_diagnostics(self):
        """
        Return diagnostic information about the WebRTC manager.
        """
        import os
        
        # Gather environment variables
        env_vars = {
            "STUN_URL": os.getenv("VITE_STUN_URL", "Not set"),
            "TURN_URL": os.getenv("VITE_TURN_URL", "Not set"),
            "TURN_USERNAME": "Set" if os.getenv("VITE_TURN_USERNAME") else "Not set",
            "TURN_PASSWORD": "Set" if os.getenv("VITE_TURN_PASSWORD") else "Not set",
        }
        
        # Gather active connections
        connections = {}
        for client_id, pc in self.peer_connections.items():
            connections[client_id] = {
                "iceConnectionState": pc.iceConnectionState,
                "connectionState": pc.connectionState if hasattr(pc, "connectionState") else "Unknown",
                "signalingState": pc.signalingState,
                "iceGatheringState": pc.iceGatheringState,
            }
            
        # Gather video track info
        video_track_info = {
            "width": self.video_track.width,
            "height": self.video_track.height,
            "fps": self.video_track.fps,
            "frames_sent": self.video_track.frames_sent,
        }
        
        return {
            "environment_variables": env_vars,
            "active_connections": connections,
            "video_quality": self.video_quality,
            "video_track": video_track_info,
        }
    
    async def add_ice_candidate(self, client_id, candidate_dict):
        """
        Process an ICE candidate received from a client
        
        Args:
            client_id: The unique identifier of the client
            candidate_dict: Dictionary containing ICE candidate information
        """
        if not client_id or not candidate_dict:
            if not client_id:
                logger.warning("Received ICE candidate with no client ID")
            else:
                logger.warning(f"Received empty ICE candidate from client {client_id}")
            return
            
        # Check if connection still exists
        if client_id not in self.peer_connections:
            logger.warning(f"Received ICE candidate for unknown client {client_id}")
            return
            
        # Update timestamp to indicate activity
        self.connection_timestamps[client_id] = time.time()
        
        # Get peer connection
        pc = self.peer_connections[client_id]
        
        # Skip if connection is in a state that can't accept candidates
        if pc.connectionState in ["closed", "failed"] or pc.iceConnectionState in ["closed", "failed"]:
            logger.warning(f"Ignoring ICE candidate for {client_id} - connection state: {pc.connectionState}")
            return
            
        try:
            # Parse ICE candidate string manually
            candidate_str = candidate_dict.get("candidate", "")
            
            # Always log ICE candidate info
            candidate_type = "unknown"
            if "typ " in candidate_str:
                candidate_type = candidate_str.split("typ ")[1].split()[0]
            logger.info(f"ICE candidate from client {client_id}: type={candidate_type}")
       
            
            # The rest of the code is skipped to avoid the error
            # Original code below is commented out
    
            # Extract IP address for network debugging if present
            if len(candidate_str.split()) >= 5:
                ip = candidate_str.split()[4]
                logger.info(f"ICE candidate IP: {ip}")
            
            # The format is typically: candidate:foundation component protocol priority ip port type ...
            # Example: candidate:0 1 UDP 2122252543 192.168.1.100 49923 typ host
            parts = candidate_str.split()
            
            # Extract required components for RTCIceCandidate
            if len(parts) >= 10 and parts[0].startswith("candidate:"):
                foundation = parts[0].split(":")[1]
                component = int(parts[1])
                protocol = parts[2]
                priority = int(parts[3])
                ip = parts[4]
                port = int(parts[5])
                # parts[6] should be "typ"
                candidate_type = parts[7]
                
                # Create a fully initialized RTCIceCandidate
                ice_candidate = RTCIceCandidate(
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
                
                # Run add ICE candidate in a protected way
                try:
                    add_task = asyncio.create_task(pc.addIceCandidate(ice_candidate))
                    await asyncio.wait_for(add_task, timeout=2.0)
                    logger.info(f"Added ICE candidate for client {client_id}")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout adding ICE candidate for {client_id}")
                except Exception as e:
                    logger.error(f"Error in addIceCandidate task: {str(e)}")
            else:
                logger.warning(f"Invalid ICE candidate format: {candidate_str}")

        except Exception as e:
            logger.error(f"Error processing ICE candidate: {str(e)}")
            traceback.print_exc() 