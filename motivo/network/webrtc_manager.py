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
import re # Need re for parsing

logger = logging.getLogger('webrtc_manager')

# Video quality configurations optimized for performance
VIDEO_CONFIGS = {
    "low": {"width": 640, "height": 360, "fps": 15},
    "medium": {"width": 854, "height": 480, "fps": 24},  # Reduced resolution, reliable framerate
    "high": {"width": 1280, "height": 720, "fps": 24},   # Reduced framerate for stability
    "hd": {"width": 1920, "height": 1080, "fps": 20}     # Further reduced framerate for high-res
}

class FrameTransformer:
    """
    Transform frames before sending over WebRTC.
    Optimized with caching and faster processing for better performance.
    """
    def __init__(self, width=640, height=480):
        self.width = width
        self.height = height
        self.last_frame = None
        
        # Cache for optimization
        self._last_input_shape = None
        self._last_src_aspect = None
        self._cached_canvas = None
        self._y_offset = 0
        self._x_offset = 0
        self._new_height = 0
        self._new_width = 0
        self._resize_method = None  # 'width', 'height', or 'direct'
        
        # Performance tracking
        self._transform_count = 0
        self._cached_transforms = 0
        self._start_time = time.time()
        
    def transform(self, frame):
        """Optimized frame processing for WebRTC with aspect ratio preservation"""
        try:
            # Skip unnecessary copying if possible
            if frame is None:
                if self.last_frame is not None:
                    return self.last_frame
                else:
                    return np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    
            # Performance tracking
            self._transform_count += 1
            
            # Check dimensions
            input_shape = frame.shape
            src_width, src_height = input_shape[1], input_shape[0]
            
            # Fast path: dimensions already match, just convert color
            if src_width == self.width and src_height == self.height:
                # Color conversion is still needed
                if input_shape[2] == 3:  # Only convert if 3-channel
                    result = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    result = frame  # Use as-is
                    
                self.last_frame = result
                return result
                
            # Check if frame dimensions match our cached calculations
            cache_hit = (input_shape == self._last_input_shape)
            
            if not cache_hit:
                # Need to recalculate transformations
                src_aspect = src_width / src_height
                dst_aspect = self.width / self.height
                self._last_input_shape = input_shape
                self._last_src_aspect = src_aspect
                
                # Determine resize method
                if abs(src_aspect - dst_aspect) < 0.01:
                    # Aspect ratios close enough, use direct resize
                    self._resize_method = 'direct'
                elif src_aspect > dst_aspect:
                    # Source is wider, scale to target width and center vertically
                    self._resize_method = 'width'
                    self._new_height = int(self.width / src_aspect)
                    self._y_offset = (self.height - self._new_height) // 2
                    # Pre-create canvas
                    self._cached_canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                else:
                    # Source is taller, scale to target height and center horizontally
                    self._resize_method = 'height'
                    self._new_width = int(self.height * src_aspect)
                    self._x_offset = (self.width - self._new_width) // 2
                    # Pre-create canvas
                    self._cached_canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            else:
                self._cached_transforms += 1
                
            # Convert color first - PyAV's VideoFrame.from_ndarray expects RGB
            if input_shape[2] == 3:  # Only convert if 3-channel
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                rgb_frame = frame  # Use as-is
                
            # Apply the appropriate transformation
            if self._resize_method == 'direct':
                # Simple resize - aspect ratios match
                result = cv2.resize(
                    rgb_frame, 
                    (self.width, self.height),
                    interpolation=cv2.INTER_AREA
                )
            elif self._resize_method == 'width':
                # Scale to width and center vertically
                scaled = cv2.resize(
                    rgb_frame, 
                    (self.width, self._new_height),
                    interpolation=cv2.INTER_AREA
                )
                # Create fresh canvas (avoid using cached one to prevent artifacts)
                canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                # Place on canvas
                canvas[self._y_offset:self._y_offset+self._new_height, 0:self.width] = scaled
                result = canvas
            else:  # self._resize_method == 'height'
                # Scale to height and center horizontally
                scaled = cv2.resize(
                    rgb_frame, 
                    (self._new_width, self.height),
                    interpolation=cv2.INTER_AREA
                )
                # Create fresh canvas
                canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                # Place on canvas
                canvas[0:self.height, self._x_offset:self._x_offset+self._new_width] = scaled
                result = canvas
                
            # Store last successfully processed frame
            self.last_frame = result
            
            # Log performance stats periodically
            elapsed = time.time() - self._start_time
            if self._transform_count % 300 == 0 and elapsed > 0:
                transforms_per_sec = self._transform_count / elapsed
                cache_ratio = (self._cached_transforms / max(1, self._transform_count)) * 100
                logger.debug(f"FrameTransformer stats: {transforms_per_sec:.1f} transforms/sec, " +
                             f"cache hit ratio: {cache_ratio:.1f}%")
                
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
    A video stream track that sends frames from the simulation with enhanced reliability.
    Uses aiortc's VideoStreamTrack with improvements for smoother playback.
    """
    def __init__(self, width=640, height=480, fps=30):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps
        
        # Target frame duration in seconds
        self.frame_duration = 1.0 / fps
        
        # Frame transformer for processing frames
        self.frame_transformer = FrameTransformer(width, height)
        
        # Use a larger queue to buffer frames during unstable periods
        # This helps prevent stream interruptions during short network issues
        self.frame_queue = asyncio.Queue(maxsize=3)
        
        # Tracking for stats and debug
        self.counter = 0
        self.frames_processed = 0
        self.dropped_frames = 0
        self.start_time = time.time()
        self.last_frame_time = time.time()
        
        # Use fractions for time_base (standard in aiortc)
        self.time_base = fractions.Fraction(1, 90000)
        
        # Error tracking
        self.consecutive_errors = 0
        
        # Last successfully processed frame (for fallback)
        self.last_frame = None
        
        # Frame timestamp tracking for smooth delivery
        self.last_pts = 0
        self.frame_interval = int(90000 / fps)  # in pts units
        
        logger.info(f"FrameVideoStreamTrack initialized: {width}x{height}@{fps}fps")
        
    def update_frame(self, frame):
        """Update the frame to be sent to connected peers with improved handling"""
        try:
            # Reset error counter on successful calls
            self.consecutive_errors = 0
            
            # Transform the frame
            processed_frame = self.frame_transformer.transform(frame)
            
            # Track successful frame processing
            self.frames_processed += 1
            current_time = time.time()
            frame_time_delta = current_time - self.last_frame_time
            self.last_frame_time = current_time
            
            # Add to queue with backpressure handling
            try:
                # Try to add to queue without waiting
                self.frame_queue.put_nowait(processed_frame)
            except asyncio.QueueFull:
                # Queue is full - we need to drop a frame
                
                # During normal operation, drop the oldest frame
                # During high load, drop all frames and just keep the newest
                if frame_time_delta > 2 * self.frame_duration:
                    # We're getting frames too slowly - clear queue and add newest
                    while not self.frame_queue.empty():
                        try:
                            _ = self.frame_queue.get_nowait()
                            self.dropped_frames += 1
                        except Exception:
                            pass
                else:
                    # Normal operation - just drop oldest frame
                    try:
                        _ = self.frame_queue.get_nowait()
                        self.dropped_frames += 1
                    except Exception:
                        pass
                
                # Now add our current frame
                try:
                    self.frame_queue.put_nowait(processed_frame)
                except asyncio.QueueFull:
                    logger.warning("Queue still full after cleanup - frame dropped")
                    self.dropped_frames += 1
                    
            # Periodically log stats
            if self.frames_processed % 300 == 0:
                drop_percent = (self.dropped_frames / max(1, self.frames_processed)) * 100
                logger.debug(f"Frame stats: processed={self.frames_processed}, dropped={self.dropped_frames} ({drop_percent:.1f}%)")
                
            # Save last successful frame for fallback
            self.last_frame = processed_frame
            
        except Exception as e:
            self.consecutive_errors += 1
            if self.consecutive_errors < 5:
                logger.error(f"Error updating frame: {e}")
            else:
                # Only log occasionally after many errors to avoid flooding logs
                if self.consecutive_errors % 100 == 0:
                    logger.error(f"Still encountering frame update errors after {self.consecutive_errors} attempts: {e}")
            
    async def recv(self):
        """Get the next frame to send with improved timing and reliability"""
        try:
            # Calculate target PTS based on smooth timing
            target_pts = 0
            if self.last_pts > 0:
                # Aim for smooth frame delivery by incrementing previous PTS
                target_pts = self.last_pts + self.frame_interval
            else:
                # First frame - base on wall clock
                target_pts = int((time.time() - self.start_time) * 90000)
            
            # Try to get a frame with timeout
            frame = None
            try:
                # Shorter timeout for more responsive frame delivery
                frame = await asyncio.wait_for(self.frame_queue.get(), timeout=0.5)
                
                # Reset error counter on successful frame fetch
                self.consecutive_errors = 0
                
            except (asyncio.TimeoutError, asyncio.QueueEmpty):
                # Use last transformed frame as fallback
                frame = self.last_frame
                
                if frame is None:
                    # Create blank RGB frame as last resort fallback
                    frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    logger.debug("Using blank frame fallback")
                else:
                    logger.debug("Using last cached frame due to queue timeout")
            
            # Convert to VideoFrame - frame should already be in RGB format
            video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
            
            # Use calculated PTS for smoother playback
            video_frame.pts = target_pts
            video_frame.time_base = self.time_base
            
            # Save for next frame calculation
            self.last_pts = target_pts
            
            self.counter += 1
            return video_frame
            
        except Exception as e:
            self.consecutive_errors += 1
            if self.consecutive_errors < 5:
                logger.error(f"Error in recv: {e}")
            else:
                # Only log occasionally after many errors
                if self.consecutive_errors % 100 == 0:
                    logger.error(f"Still encountering recv errors after {self.consecutive_errors} attempts: {e}")
                
            # Create blank frame as ultimate fallback
            blank_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            
            # Try to maintain proper timing even in error case
            target_pts = 0
            if self.last_pts > 0:
                target_pts = self.last_pts + self.frame_interval
            else:
                target_pts = int((time.time() - self.start_time) * 90000)
                
            video_frame = av.VideoFrame.from_ndarray(blank_frame, format="rgb24")
            video_frame.pts = target_pts
            video_frame.time_base = self.time_base
            
            # Save for next frame
            self.last_pts = target_pts
            
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
        """Add an ICE candidate - parsing the string to match the runtime's expected signature."""
        try:
            if not candidate_dict or client_id not in self.peer_connections:
                logger.warning(f"Cannot add ICE candidate for non-existent client {client_id}")
                return False

            pc = self.peer_connections[client_id]
            
            # Extract core info
            sdpMid = candidate_dict.get("sdpMid")
            sdpMLineIndex = candidate_dict.get("sdpMLineIndex")
            candidate_string = candidate_dict.get("candidate", "")

            if not candidate_string:
                # Empty candidate string signals end-of-candidates
                logger.debug(f"Received end-of-candidates signal for {client_id}")
                # aiortc's addIceCandidate expects None for end-of-candidates
                # However, the underlying aioice might expect an empty candidate object?
                # Let's try passing None first, as per aiortc docs for addIceCandidate
                # If pc.addIceCandidate is the modern one, it should handle None correctly.
                await pc.addIceCandidate(None) 
                return True

            # --- Parse the candidate string ---
            # Example: "candidate:foundation 1 component protocol priority ip port typ type [raddr ip] [rport port] ..."
            parts = candidate_string.split()

            if not parts or not parts[0].startswith("candidate:"):
                 logger.error(f"Invalid candidate string format for {client_id}: {candidate_string}")
                 return False
                 
            foundation = parts[0].split(":")[1]
            component_id = int(parts[1]) # 1 for RTP, 2 for RTCP
            protocol = parts[2].lower()
            priority = int(parts[3])
            ip = parts[4]
            port = int(parts[5])
            
            # Find 'typ' and the actual type value
            try:
                 typ_index = parts.index("typ")
                 candidate_type = parts[typ_index + 1]
            except (ValueError, IndexError):
                 logger.error(f"Could not find 'typ' in candidate string for {client_id}: {candidate_string}")
                 return False
            
            # Extract optional related address and port
            related_address = None
            related_port = None
            try:
                raddr_index = parts.index("raddr")
                related_address = parts[raddr_index + 1]
            except ValueError:
                pass # Optional
            try:
                rport_index = parts.index("rport")
                related_port = int(parts[rport_index + 1])
            except ValueError:
                pass # Optional
                
            # Extract optional tcp type
            tcp_type = None
            try:
                 tcptype_index = parts.index("tcptype")
                 tcp_type = parts[tcptype_index + 1]
            except ValueError:
                pass # Optional

            ice_candidate = None # Initialize variable
            
            # --- Attempt 1: Use the older-style positional constructor (currently working) ---
            try:
                 logger.debug(f"Attempting RTCIceCandidate with positional args for {client_id}")
                 ice_candidate = RTCIceCandidate(
                     component=component_id, foundation=foundation, ip=ip, port=port,
                     priority=priority, protocol=protocol, type=candidate_type,
                     relatedAddress=related_address, relatedPort=related_port,
                     sdpMid=sdpMid, sdpMLineIndex=sdpMLineIndex, tcpType=tcp_type
                 )
                 logger.info(f"Successfully created RTCIceCandidate using positional args for {client_id}")
            except TypeError as te_pos:
                 logger.warning(f"Positional RTCIceCandidate constructor failed ({type(te_pos).__name__}: {te_pos}). Will attempt keyword constructor.")
                 # --- Attempt 2: Fallback to modern keyword constructor (sdp=) ---
                 try:
                     logger.debug(f"Attempting RTCIceCandidate with keyword args for {client_id}")
                     ice_candidate = RTCIceCandidate(
                         sdp=candidate_string,
                         sdpMid=sdpMid,
                         sdpMLineIndex=sdpMLineIndex
                         # Optional: usernameFragment=... if needed
                     )
                     logger.info(f"Successfully created RTCIceCandidate using keyword args (fallback) for {client_id}")
                 except TypeError as te_kw:
                     logger.error(f"Keyword RTCIceCandidate constructor also failed ({type(te_kw).__name__}: {te_kw}). Cannot create candidate.")
                     # Log details from both attempts if keyword fails
                     logger.error(f"Positional attempt error: {te_pos}")
                     logger.error(f"Keyword attempt error: {te_kw}")
                     return False
                 except Exception as create_err_kw:
                     logger.error(f"Unexpected error creating RTCIceCandidate with keyword args: {create_err_kw}")
                     return False
            except Exception as create_err_pos:
                 logger.error(f"Unexpected error creating RTCIceCandidate with positional args: {create_err_pos}")
                 return False
            
            # If we successfully created an ice_candidate object via either method:
            if ice_candidate is None:
                 logger.error("RTCIceCandidate object is None after attempting both methods. This should not happen.")
                 return False
                 
            # Add the created candidate to the peer connection
            await pc.addIceCandidate(ice_candidate)
            logger.debug(f"Passed candidate object to pc.addIceCandidate for {client_id}")
            return True

        except Exception as e:
            # Log the specific exception type and message
            logger.error(f"Error processing ICE candidate string for {client_id} ({type(e).__name__}): {e}")
            import traceback
            logger.error(traceback.format_exc()) # Log full traceback for parsing errors
            return False
            
    async def broadcast_frame(self, frame):
        """Send a frame to all connected peers with enhanced reliability"""
        if not self.tracks:
            return 0
            
        try:
            if frame is None:
                # Skip empty frames
                return 0
            
            # Frame buffer management - only update frame if it's different
            # This reduces processing load when frames haven't changed
            frame_hash = hash(frame.tobytes()) if hasattr(frame, 'tobytes') else None
            if frame_hash == getattr(self, '_last_frame_hash', None):
                # Frame identical to previous one - might be a duplicate
                # Still count as updated but skip processing
                return len(self.tracks)
            
            # Store hash for next comparison        
            self._last_frame_hash = frame_hash
                
            # Rate limiting for busy periods - if more than 10 frames
            # are waiting to be processed, we might be backlogged
            # In that case, temporarily reduce processing load
            current_time = time.time()
            if not hasattr(self, '_last_broadcast_time'):
                self._last_broadcast_time = current_time
                self._broadcast_backlog = 0
            else:
                time_delta = current_time - self._last_broadcast_time
                self._last_broadcast_time = current_time
                
                # If frames are arriving too quickly, increment backlog
                if time_delta < 0.01:  # Less than 10ms between frames
                    self._broadcast_backlog += 1
                else:
                    # Otherwise, gradually reduce backlog
                    self._broadcast_backlog = max(0, self._broadcast_backlog - 1)
                
                # If we have significant backlog, process only every Nth frame
                if self._broadcast_backlog > 10:
                    # Skip this frame if it's not a multiple of throttle factor
                    throttle_factor = min(5, self._broadcast_backlog // 10 + 1)
                    if getattr(self, '_frame_counter', 0) % throttle_factor != 0:
                        self._frame_counter = getattr(self, '_frame_counter', 0) + 1
                        return 0
                        
            self._frame_counter = getattr(self, '_frame_counter', 0) + 1
                
            # Update all tracks
            updated = 0
            closed_connections = []
            
            for client_id, track in list(self.tracks.items()):
                try:
                    # Verify connection is still active
                    if client_id in self.peer_connections:
                        pc = self.peer_connections[client_id]
                        if pc.connectionState != "closed" and pc.connectionState != "failed":
                            track.update_frame(frame)
                            updated += 1
                        else:
                            # Mark for cleanup
                            closed_connections.append(client_id)
                    else:
                        # Track exists but connection doesn't - clean up
                        closed_connections.append(client_id)
                except Exception as e:
                    logger.error(f"Error updating track for {client_id}: {e}")
                    # If error occurs multiple times, mark for cleanup
                    if not hasattr(track, '_error_count'):
                        track._error_count = 1
                    else:
                        track._error_count += 1
                        
                    if track._error_count > 5:
                        closed_connections.append(client_id)
            
            # Clean up closed connections
            for client_id in closed_connections:
                logger.info(f"Scheduling cleanup for connection {client_id}")
                # Schedule cleanup to avoid blocking
                asyncio.create_task(self.close_connection(client_id))
                    
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