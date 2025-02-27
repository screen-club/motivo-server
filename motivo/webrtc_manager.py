import asyncio
import cv2
import json
import uuid
from typing import Dict, Set, Any, Tuple
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCConfiguration
from aiortc.contrib.media import MediaStreamTrack
import numpy as np
import fractions
import traceback

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
                    print(f"Error resizing frame: {str(e)}")
                    # Create a blank frame of the target size as a fallback
                    processed_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            
            # Put new frame in queue
            self.queue.put_nowait(processed_frame)
        except Exception as e:
            print(f"Error updating frame: {str(e)}")
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
            else:
                frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
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
            # Make a copy to avoid modifying the original
            processed_frame = frame.copy()
            
            # Convert from BGR (from DisplayManager) back to RGB for WebRTC
            if processed_frame.shape[2] == 3:
                processed_frame = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
            
            # Update the video track with the RGB frame
            self.video_track.update_frame(processed_frame)
        except Exception as e:
            print(f"Error updating frame: {str(e)}")
            # If update fails, try to send an empty frame
            try:
                blank_frame = np.zeros((self.video_track.height, self.video_track.width, 3), dtype=np.uint8)
                self.video_track.update_frame(blank_frame)
            except:
                print(f"Failed to send blank frame after error")
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
            
        # Create a RTCPeerConnection with default configuration
        # Let aiortc handle the ICE server configuration internally
        pc = RTCPeerConnection()
        
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
                    print(f"Set max bitrate to {max_bitrate/1_000_000}Mbps for {client_id}")
        except Exception as e:
            print(f"Error setting encoding parameters: {str(e)}")
        
        # Handle ICE connection state changes
        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            print(f"ICE connection state for {client_id}: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed" or pc.iceConnectionState == "closed":
                # Use a safe closure method to prevent KeyErrors
                await self.safe_close_peer_connection(client_id)
        
        # Handle connection state changes
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state for {client_id}: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                # Use a safe closure method to prevent KeyErrors
                await self.safe_close_peer_connection(client_id)
        
        return pc, client_id
    
    async def handle_offer(self, client_id, sdp):
        """
        Handle a WebRTC offer from a client.
        """
        print(f"Received WebRTC offer from client {client_id}")
        
        try:
            # Check if we already have an existing connection that might be stale
            if client_id in self.peer_connections:
                pc = self.peer_connections[client_id]
                # Check connection state more thoroughly
                if pc.connectionState in ["failed", "closed", "disconnected"] or pc.iceConnectionState in ["failed", "closed", "disconnected"]:
                    print(f"Replacing stale peer connection for client {client_id}")
                    # Close old connection safely first
                    await self.safe_close_peer_connection(client_id)
                    # Then create a new one
                    pc, _ = await self.create_peer_connection(client_id)
                else:
                    print(f"Using existing peer connection for client {client_id}")
                    
                    # Double-check if the connection is actually usable
                    # This helps prevent "RTCPeerConnection is closed" errors
                    if hasattr(pc, '_isClosed') and pc._isClosed:
                        print(f"Connection marked as closed internally, creating new connection for {client_id}")
                        await self.safe_close_peer_connection(client_id)
                        pc, _ = await self.create_peer_connection(client_id)
            else:
                print(f"Creating new peer connection for client {client_id}")
                pc, _ = await self.create_peer_connection(client_id)
            
            # Set the remote description
            offer = RTCSessionDescription(sdp=sdp, type="offer")
            await pc.setRemoteDescription(offer)
            print(f"Set remote description for client {client_id}")
            
            # Create an answer
            try:
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                print(f"Created answer for client {client_id}: {answer.type}")
                
                return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
            except Exception as e:
                # If answer creation fails, it might be due to invalid state
                print(f"Error creating answer: {str(e)}")
                if "is closed" in str(e):
                    # Connection is closed, create a new one and try again
                    print(f"Connection was closed, creating new connection for {client_id}")
                    await self.safe_close_peer_connection(client_id)
                    pc, _ = await self.create_peer_connection(client_id)
                    
                    # Try again with the new connection
                    offer = RTCSessionDescription(sdp=sdp, type="offer")
                    await pc.setRemoteDescription(offer)
                    answer = await pc.createAnswer()
                    await pc.setLocalDescription(answer)
                    print(f"Created answer with new connection for {client_id}: {answer.type}")
                    
                    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
                else:
                    # Rethrow other errors
                    raise
        except Exception as e:
            print(f"Error handling WebRTC offer: {str(e)}")
            traceback.print_exc()
            
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
        Safely close a peer connection with protection against concurrent closures.
        """
        try:
            if client_id in self.peer_connections:
                pc = self.peer_connections[client_id]
                # Remove from dictionary first to prevent other callbacks from attempting closure
                del self.peer_connections[client_id]
                # Then close the connection
                await pc.close()
                print(f"Safely closed peer connection for {client_id}")
            # If client_id is not in peer_connections, it may have already been closed
        except Exception as e:
            print(f"Error during safe connection closure for {client_id}: {str(e)}")
    
    async def close_peer_connection(self, client_id):
        """
        Close a peer connection.
        """
        # Forward to the safe implementation
        await self.safe_close_peer_connection(client_id)
    
    async def close_all_connections(self):
        """
        Close all peer connections.
        """
        # Make a copy of the keys to avoid modification during iteration
        client_ids = list(self.peer_connections.keys())
        for client_id in client_ids:
            await self.safe_close_peer_connection(client_id) 