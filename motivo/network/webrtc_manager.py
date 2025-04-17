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
import socket
import ipaddress


logger = logging.getLogger('webrtc_manager')

# Helper function to check for private IP addresses
def is_private_ip(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check for private ranges (IPv4/IPv6) and loopback
        return ip.is_private or ip.is_loopback
    except ValueError:
        # Invalid IP string
        return False

class FrameVideoStreamTrack(VideoStreamTrack):
    """
    A video stream track that provides frames from the simulation.
    """

    def __init__(self, width=640, height=480, fps=30):
        super().__init__()
        self.latest_frame = None
        # Increase queue size to handle network jitter better
        self.queue = asyncio.Queue(maxsize=3)
        self.frame_count = 0
        self.width = width
        self.height = height
        self.fps = fps
        self.time_base = fractions.Fraction(1, fps)
        self.frames_sent = 0
        self.last_frame_time = time.time()
        self.frame_delivery_times = []  # Track frame timing for adaptive rate control
        logger.debug(f"Created video track with resolution {width}x{height} @ {fps}fps")
        
    def update_frame(self, frame):
        """Update the latest frame to be sent to connected peers"""
        try:
            # Update timing for adaptive rate control
            now = time.time()
            frame_interval = now - self.last_frame_time
            self.last_frame_time = now
            
            # Track delivery times for last 30 frames
            self.frame_delivery_times.append(frame_interval)
            if len(self.frame_delivery_times) > 30:
                self.frame_delivery_times.pop(0)
            
            # If queue is getting full, reduce frame quality instead of dropping
            quality_factor = 1.0  # Full quality
            if self.queue.qsize() >= 2:
                # If we're starting to build up a backlog, reduce quality
                quality_factor = 0.5
                logger.debug("Queue backlog detected, reducing frame quality")
                
            # Process frame - make a copy to avoid modifying the original
            processed_frame = frame.copy()
            
            # NOTE: Frames should already be in RGB format from the simulation loop
            # env.render() returns RGB frames which are passed directly to this track
            
            # Resize frame to target resolution if needed with adaptive quality
            if (processed_frame.shape[1] != self.width or 
                processed_frame.shape[0] != self.height):
                try:
                    # Use high-quality interpolation for resizing when queue is not full
                    # Otherwise use faster but lower quality resizing
                    interpolation = cv2.INTER_AREA if quality_factor < 1.0 else cv2.INTER_LANCZOS4
                    
                    processed_frame = cv2.resize(
                        processed_frame, 
                        (self.width, self.height), 
                        interpolation=interpolation
                    )
                except Exception as e:
                    logger.error(f"Error resizing frame: {str(e)}")
                    # Fall back to a simpler method
                    try:
                        processed_frame = cv2.resize(
                            processed_frame, 
                            (self.width, self.height), 
                            interpolation=cv2.INTER_NEAREST
                        )
                    except:
                        # Create a blank frame of the target size as a last resort
                        processed_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            
            # Put frame in queue with error handling
            try:
                # Try to add to queue, but don't block
                self.queue.put_nowait(processed_frame)
                self.frame_count += 1
            except asyncio.QueueFull:
                # If queue is full, replace oldest frame instead of dropping
                try:
                    # Remove oldest frame
                    self.queue.get_nowait()
                    # Add new frame
                    self.queue.put_nowait(processed_frame)
                    self.frame_count += 1
                    logger.debug("Queue full, replaced oldest frame")
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    # Last resort fallback
                    logger.warning("Failed to update frame queue - queue state inconsistent")
            
        except Exception as e:
            logger.error(f"Error updating frame: {e}")
            traceback.print_exc()
    
    async def recv(self):
        """Get the latest frame to send to the client"""
        try:
            # Calculate adaptive timeout based on network conditions
            # If we've been having slow delivery, use a longer timeout
            adaptive_timeout = 3.0  # Default longer timeout for better resilience
            if len(self.frame_delivery_times) > 5:
                # Calculate average and max frame intervals
                avg_interval = sum(self.frame_delivery_times) / len(self.frame_delivery_times)
                max_interval = max(self.frame_delivery_times)
                
                # Set timeout to be at least 3x the average frame time or 1.5x the max
                # This allows for network jitter while preventing too long delays
                adaptive_timeout = max(3.0 * avg_interval, 1.5 * max_interval, 2.0)
                adaptive_timeout = min(adaptive_timeout, 5.0)  # Cap at 5 seconds
            
            # Get frame with adaptive timeout
            try:
                frame = await asyncio.wait_for(self.queue.get(), timeout=adaptive_timeout)
            except (asyncio.QueueEmpty, asyncio.TimeoutError):
                # Create a blank frame if no frame is available
                if hasattr(self, 'latest_frame') and self.latest_frame is not None:
                    frame = self.latest_frame
                    if self.frame_count % 30 == 0:  # Log every 30 frames (1 second at 30 fps)
                        logger.warning(f"Using previous frame - no new frame received after {adaptive_timeout:.1f}s timeout")
                else:
                    frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    if self.frame_count % 30 == 0:  # Log every 30 frames
                        logger.warning(f"Sending blank frame - no frames available after {adaptive_timeout:.1f}s timeout")
            
            # Store latest frame for backup
            self.latest_frame = frame
            self.frames_sent += 1
            
            # Check if we need to adapt quality based on timing
            now = time.time()
            frame_time = now - self.last_frame_time
            self.last_frame_time = now
            
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
        import os
        
        # --- Network Environment Detection ---
        is_potentially_online = False
        try:
            hostname = socket.gethostname()
            addrinfo = socket.getaddrinfo(hostname, None)
            local_ips = set()
            for item in addrinfo:
                # item[4] is the sockaddr tuple, item[4][0] is the IP address
                ip = item[4][0]
                local_ips.add(ip)
                if not is_private_ip(ip):
                    # Found a non-private, non-loopback IP, assume online
                    is_potentially_online = True
                    logger.debug(f"Detected potentially public IP: {ip}")
                    break 
            if not is_potentially_online:
                 logger.debug(f"Detected only private/loopback IPs: {local_ips}")
        except socket.gaierror:
            logger.warning("Could not determine local IP addresses via hostname lookup.")
            # Fallback: Assume potentially online to be safe, use env var if needed?
            # For now, we'll assume online as a safer default if detection fails.
            is_potentially_online = True 
        # --- End Network Environment Detection ---

        ice_servers = []
        if not is_potentially_online:
            logger.info("Detected local/private network - skipping external ICE servers.")
        else:
            logger.info("Detected potentially online network - configuring external ICE servers.")
            # Get STUN/TURN server info from environment (or use default)
            # Multiple STUN servers for redundancy
            stun_urls = [
                "stun:stun.l.google.com:19302",  # Google STUN
                "stun:stun1.l.google.com:19302", # Google STUN backup
                "stun:stun.stunprotocol.org:3478" # Open STUN project
            ]
            
            # Use configured STUN or default to the first in our list
            # Use os.environ.get("VITE_STUN_URL", ...) for consistency with frontend naming
            stun_url_config = os.environ.get("VITE_STUN_URL")
            if stun_url_config:
                stun_urls = [stun_url_config] # Override defaults if specific one is provided

            turn_url = os.environ.get("VITE_TURN_URL", "")
            turn_username = os.environ.get("VITE_TURN_USERNAME", "")
            turn_password = os.environ.get("VITE_TURN_PASSWORD", "")
            
            # Add multiple STUN servers for redundancy
            ice_servers.append(RTCIceServer(urls=stun_urls))
            
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
                    # Fix duplicate prefix bug by not replacing turn: with turn: again
                    tcp_turn_url = turn_url + "?transport=tcp"
                    ice_servers.append(
                        RTCIceServer(
                            urls=[tcp_turn_url],
                            username=turn_username,
                            credential=turn_password
                        )
                    )
                    
                # TURNS (TURN over TLS for secure connections)
                # Note: TURNS often uses a different port (e.g., 5349 or 443)
                # Ensure the VITE_TURN_URL is correct for TURNS if used.
                if turn_url.startswith("turn:"):
                    # Simple replacement might not be enough if port needs changing
                    turns_url = turn_url.replace("turn:", "turns:") 
                    ice_servers.append(
                        RTCIceServer(
                            urls=[turns_url],
                            username=turn_username,
                            credential=turn_password
                        )
                    )
        
        logger.info(f"Initialized with {len(ice_servers)} ICE servers.")
        
        # Configure RTCConfiguration
        self.rtc_configuration = RTCConfiguration(iceServers=ice_servers)
        
        # Store peer connections
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.tracks: Dict[str, FrameVideoStreamTrack] = {}
        self.connection_monitoring_tasks = {}
        
        # Set default video quality
        self.set_video_quality(video_quality)
        
        # Environment reference (set later)
        self.env = None
        
        # Connection stats
        self.connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "recovered_connections": 0
        }
        
        logger.debug(f"WebRTC manager initialized with {video_quality} quality")
    
    def set_environment(self, env):
        """Set the environment reference"""
        self.env = env
        logger.debug("Environment set in WebRTC manager")
        
        # Start connection health monitor
        self._start_connection_health_monitor()
    
    def _start_connection_health_monitor(self):
        """Start a background task to monitor connection health"""
        async def health_monitor():
            try:
                while True:
                    await asyncio.sleep(15)  # Check every 15 seconds
                    await self._check_connection_health()
            except asyncio.CancelledError:
                logger.debug("Connection health monitor stopped")
            except Exception as e:
                logger.error(f"Error in connection health monitor: {e}")
                traceback.print_exc()
        
        # Create the task
        asyncio.create_task(health_monitor())
        logger.debug("Started WebRTC connection health monitor")
    
    async def _check_connection_health(self):
        """Check health of all active connections"""
        # Skip if no connections
        if not self.peer_connections:
            return
            
        logger.debug(f"Checking health of {len(self.peer_connections)} WebRTC connections")
        
        # Track issues for reporting
        stale_connections = []
        recovering_connections = []
        healthy_connections = []
        
        # Current time for age calculations
        now = time.time()
        
        # Check each connection
        for client_id, pc in list(self.peer_connections.items()):
            try:
                # Check if connection is stale (no activity for a longer period)
                if hasattr(pc, '_last_active_time'):
                    inactive_time = now - pc._last_active_time
                    if inactive_time > 60: # Increased stale threshold to 60s
                        stale_connections.append(client_id)
                        
                        # If very stale (3+ minutes), close it
                        if inactive_time > 180: # Increased closing threshold to 180s
                            logger.warning(f"Connection {client_id} inactive for {inactive_time:.1f}s, closing")
                            await self.close_connection(client_id)
                            continue
                
                # Check connection state - using string comparison for safety
                # Since connectionState might be a property with its own type
                conn_state = str(pc.connectionState)
                ice_state = str(pc.iceConnectionState)
                
                if conn_state in ["connected", "completed"] or ice_state in ["connected", "completed"]:
                    healthy_connections.append(client_id)
                elif conn_state in ["disconnected", "failed"] or ice_state in ["disconnected", "failed"]:
                    recovering_connections.append(client_id)
                    
                    # Start recovery if not already monitored
                    if client_id not in self.connection_monitoring_tasks:
                        logger.info(f"Starting recovery for {client_id} in state {pc.connectionState}")
                        task = asyncio.create_task(self.monitor_connection(client_id, pc))
                        self.connection_monitoring_tasks[client_id] = task
                
            except Exception as e:
                logger.error(f"Error checking connection {client_id}: {e}")
        
        # Log connection health summary
        if healthy_connections or recovering_connections or stale_connections:
            logger.debug(f"Connection health: {len(healthy_connections)} healthy, " + 
                        f"{len(recovering_connections)} recovering, " +
                        f"{len(stale_connections)} stale")
        
    def set_video_quality(self, quality_name):
        """Set the video quality for new connections"""
        if quality_name in VIDEO_CONFIGS:
            self.video_config = VIDEO_CONFIGS[quality_name]
            logger.debug(f"Video quality set to {quality_name}: {self.video_config}")
        else:
            logger.warning(f"Unknown quality '{quality_name}', using medium")
            self.video_config = VIDEO_CONFIGS["medium"]
        
        # Track connection creation
        logger.debug(f"Created video track with resolution {self.video_config['width']}x{self.video_config['height']} @ {self.video_config['fps']}fps")
    
    async def create_peer_connection(self, client_id, offer):
        """Create a new peer connection for a client"""
        try:
            # If there's an existing connection for this client, close it first
            if client_id in self.peer_connections:
                logger.info(f"Closing existing connection for client {client_id} before creating a new one")
                await self.close_connection(client_id)
            
            # Create a new peer connection with enhanced configuration
            pc = RTCPeerConnection(configuration=self.rtc_configuration)
            
            # Update connection stats
            self.connection_stats["total_connections"] += 1
            self.connection_stats["active_connections"] += 1
            
            # Add peer connection start time for monitoring
            pc._creation_time = time.time()
            pc._last_active_time = time.time()
            
            # Register callback handlers for connection state monitoring
            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                pc._last_active_time = time.time()
                ice_state = str(pc.iceConnectionState)
                logger.debug(f"ICE Connection state for {client_id}: {ice_state}")
                
                # Handle specific connection states
                if ice_state == "checking":
                    # Connection is being established, might need more time
                    logger.debug(f"ICE negotiation in progress for {client_id}")
                    
                elif ice_state in ["connected", "completed"]:
                    # Connection established successfully
                    logger.debug(f"ICE connection established for {client_id}")
                    # Cancel any pending recovery tasks
                    if client_id in self.connection_monitoring_tasks:
                        task = self.connection_monitoring_tasks.pop(client_id)
                        if not task.done():
                            task.cancel()
                        # Track successful recovery
                        self.connection_stats["recovered_connections"] += 1
                
                elif ice_state == "disconnected":
                    # Temporary disconnection - start monitoring
                    logger.warning(f"ICE connection temporarily disconnected for {client_id}")
                    # Create a monitoring task with recovery attempts
                    if client_id not in self.connection_monitoring_tasks:
                        task = asyncio.create_task(self.monitor_connection(client_id, pc))
                        self.connection_monitoring_tasks[client_id] = task
                
                elif ice_state == "failed":
                    # Persistent failure after recovery attempts
                    logger.error(f"ICE connection failed for {client_id} after recovery attempts")
                    self.connection_stats["failed_connections"] += 1
                    await self.close_connection(client_id)
                
                elif ice_state == "closed":
                    # Connection explicitly closed
                    logger.debug(f"ICE connection closed for {client_id}")
                    await self.close_connection(client_id)
            
            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                pc._last_active_time = time.time()
                conn_state = str(pc.connectionState)
                logger.debug(f"Connection state for {client_id}: {conn_state}")
                
                if conn_state == "failed":
                    # Only close after monitoring has had a chance to recover
                    if client_id in self.connection_monitoring_tasks:
                        task = self.connection_monitoring_tasks.pop(client_id)
                        if not task.done():
                            task.cancel()
                    logger.error(f"Connection persistently failed for {client_id}")
                    self.connection_stats["failed_connections"] += 1
                    await self.close_connection(client_id)
                
                elif conn_state == "closed":
                    # Connection explicitly closed
                    await self.close_connection(client_id)
            
            # Create a video track with the current quality settings
            track = FrameVideoStreamTrack(
                width=self.video_config["width"],
                height=self.video_config["height"],
                fps=self.video_config["fps"]
            )
            
            # Add track to peer connection
            pc.addTrack(track)
            
            # Process the offer - without tight timeouts, as they're causing issues
            offer_obj = RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
            await pc.setRemoteDescription(offer_obj)
            
            # Create answer without timeout restrictions
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            # Store the connection and track
            self.peer_connections[client_id] = pc
            self.tracks[client_id] = track
            
            logger.debug(f"Created peer connection for client {client_id}")
            
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
            if not candidate:
                # This is normal, often signals end-of-candidates
                logger.debug(f"Received empty candidate for client {client_id}")
                return True
            
            if client_id in self.peer_connections:
                pc = self.peer_connections[client_id]
                
                # Handle different candidate formats from browsers
                if isinstance(candidate, dict):
                    # Extract the raw SDP candidate string
                    candidate_str = candidate.get("candidate", "")
                    sdp_mid = candidate.get("sdpMid") # Keep sdpMid for context
                    sdp_mline_index = candidate.get("sdpMLineIndex") # Keep sdpMLineIndex
                    
                    if not candidate_str:
                        # Empty candidate string is normal (end of candidates)
                        logger.debug(f"Received candidate object with empty candidate string for {client_id}")
                        return True
                    
                    # Use RTCIceCandidate.from_sdp to parse the candidate string
                    try:
                        # Prepend 'a=' if not present (standard SDP format is 'a=candidate...')
                        if not candidate_str.startswith("candidate:"):
                            # It's unusual for it not to start with 'candidate:', but handle just in case
                            logger.warning(f"Candidate string for {client_id} missing 'candidate:' prefix: {candidate_str}")
                            # Attempt parsing anyway, might work depending on aiortc version
                        
                        # We need sdpMid and sdpMLineIndex for context when adding
                        # aiortc expects the full candidate line including 'a=' prefix
                        full_sdp_line = f"a=candidate:{candidate_str}" 

                        # Parse the full SDP line using from_sdp
                        # Note: from_sdp might not exist in all aiortc versions. 
                        # If it doesn't, we might need manual parsing or library update.
                        if hasattr(RTCIceCandidate, 'from_sdp'):
                            candidate_obj = RTCIceCandidate.from_sdp(full_sdp_line)
                            # Ensure sdpMid and sdpMLineIndex are set correctly from the original dict
                            # as from_sdp might not capture them depending on format.
                            candidate_obj.sdpMid = sdp_mid
                            candidate_obj.sdpMLineIndex = sdp_mline_index
                        else:
                             # Fallback if from_sdp is not available (older aiortc?) - Requires manual parsing
                             logger.warning("RTCIceCandidate.from_sdp not found. Manually parsing candidate string.")
                             try:
                                 # Basic SDP candidate line parsing: a=candidate:<foundation> <component-id> <transport> <priority> <connection-address> <port> typ <candidate-type> ...
                                 # Example: a=candidate:4234997325 1 udp 2043278322 192.168.1.100 52482 typ host ...
                                 
                                 # Remove 'a=candidate:' prefix if present for easier splitting
                                 if full_sdp_line.startswith("a=candidate:"):
                                     parts_str = full_sdp_line[len("a=candidate:"):]
                                 else:
                                     parts_str = candidate_str # Use the original candidate string if prefix missing
                                     
                                 parts = parts_str.split()
                                 
                                 if len(parts) < 8 or parts[6] != 'typ':
                                     raise ValueError(f"Invalid candidate format: cannot find required fields. Parts: {parts}")

                                 foundation = parts[0]
                                 component = int(parts[1])
                                 protocol = parts[2].lower()
                                 priority = int(parts[3])
                                 ip = parts[4]
                                 port = int(parts[5])
                                 typ = parts[7]
                                 
                                 # Construct the object using parsed values and context from the dictionary
                                 candidate_obj = RTCIceCandidate(
                                    component=component,
                                    foundation=foundation,
                                    ip=ip, 
                                    port=port,
                                    priority=priority,
                                    protocol=protocol,
                                    type=typ,
                                    sdpMid=sdp_mid, # From original dict
                                    sdpMLineIndex=sdp_mline_index # From original dict
                                 )
                                 logger.debug(f"Manually parsed candidate: {candidate_obj}")
                             except Exception as parse_exc:
                                 logger.error(f"Failed to manually parse candidate string for {client_id}: {parse_exc}\nSDP Line: {full_sdp_line}")
                                 # As a last resort, try constructing with whatever the dict provided, might still fail
                                 logger.warning(f"Falling back to potentially incomplete dictionary construction for {client_id}")
                                 candidate_obj = RTCIceCandidate(
                                    component=candidate.get("component", 0),
                                    foundation=candidate.get("foundation", ""),
                                    ip=candidate.get("ip", ""), # Might be missing/wrong
                                    port=candidate.get("port", 0),
                                    priority=candidate.get("priority", 0),
                                    protocol=candidate.get("protocol", ""),
                                    type=candidate.get("type", ""),
                                    sdpMid=sdp_mid,
                                    sdpMLineIndex=sdp_mline_index
                                 )

                        await pc.addIceCandidate(candidate_obj)
                        logger.debug(f"Added ICE candidate for client {client_id} (sdpMid={sdp_mid}, mLineIndex={sdp_mline_index})")
                        return True
                    except Exception as e:
                        logger.error(f"Error parsing/adding ICE candidate string for {client_id}: {e}\nCandidate Dict: {candidate}\nCandidate Str: {candidate_str}")
                        traceback.print_exc()
                        return False # Indicate failure
                else:
                    logger.warning(f"Unexpected candidate format for {client_id}: {type(candidate)}")
                    return False
            else:
                logger.debug(f"No peer connection found for client {client_id} to add ICE candidate")
                return False
        except Exception as e:
            logger.error(f"Error adding ICE candidate: {e}")
            traceback.print_exc()
            return False
    
    async def monitor_connection(self, client_id, pc, max_attempts=7): # Increased max_attempts
        """Monitor and attempt to recover disconnected connections"""
        try:
            attempts = 0
            while attempts < max_attempts:
                # Wait and check connection state with increased backoff
                await asyncio.sleep(3 * (attempts + 1))  # Increased base delay: 3s, 6s, 9s, etc.
                
                # Check if connection has recovered on its own
                ice_state = str(pc.iceConnectionState)
                conn_state = str(pc.connectionState)
                
                if ice_state in ["connected", "completed"] or conn_state == "connected":
                    logger.info(f"Connection for {client_id} recovered automatically")
                    return
                
                # Check if connection is permanently closed 
                if ice_state == "closed" or conn_state == "closed":
                    logger.info(f"Connection for {client_id} permanently closed, stopping recovery")
                    return
                    
                # Still disconnected, try recovery action
                attempts += 1
                logger.warning(f"Connection still {pc.iceConnectionState} for {client_id}, recovery attempt {attempts}/{max_attempts}")
                
                # Try to restart ICE
                try:
                    # Restartice is only implemented in newer versions
                    if hasattr(pc, "restartIce") and callable(pc.restartIce):
                        await pc.restartIce()
                        logger.info(f"ICE restart initiated for {client_id}")
                    else:
                        # Fallback for older aiortc versions
                        logger.warning(f"ICE restart not available in this version of aiortc")
                        
                except Exception as e:
                    logger.error(f"Error during ICE restart for {client_id}: {e}")
            
            # If we've reached max attempts and still disconnected, consider it failed
            if pc.iceConnectionState in ["disconnected", "failed"] or pc.connectionState in ["disconnected", "failed"]:
                logger.error(f"Connection recovery failed after {max_attempts} attempts for {client_id}")
        
        except asyncio.CancelledError:
            # Task was cancelled (likely because connection recovered)
            logger.debug(f"Connection monitoring for {client_id} cancelled")
        
        except Exception as e:
            logger.error(f"Error in connection monitoring for {client_id}: {e}")
            traceback.print_exc()
            
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
                
            if self._frame_count % 500 == 0:  # Reduced frequency of logging
                logger.debug(f"Frame stats: shape={frame.shape}, dtype={frame.dtype}, min={frame.min()}, max={frame.max()}")
                
            # Make a single copy for all tracks to share (more efficient)
            frame_rgb = frame.copy()
            
            # Maintain a set of completed tasks to avoid memory leaks
            tasks = set()
            update_count = 0
            
            # First filter out any closed connections
            active_tracks = {}
            for client_id, track in self.tracks.items():
                if client_id in self.peer_connections:
                    pc = self.peer_connections[client_id]
                    conn_state = str(pc.connectionState)
                    if conn_state not in ["closed", "failed"]:
                        active_tracks[client_id] = track
            
            # Update active tracks only
            for client_id, track in active_tracks.items():
                try:
                    # Use a shared frame to avoid excess copying
                    track.update_frame(frame_rgb)
                    update_count += 1
                except Exception as e:
                    logger.error(f"Error updating track for client {client_id}: {e}")
            
            # Clean up any lingering tasks periodically 
            if self._frame_count % 100 == 0 and hasattr(self, 'connection_monitoring_tasks'):
                # Remove completed monitoring tasks
                completed = []
                for cid, task in self.connection_monitoring_tasks.items():
                    if task.done():
                        completed.append(cid)
                        
                for cid in completed:
                    self.connection_monitoring_tasks.pop(cid)
            
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
                
                # Cancel any monitoring tasks for this client
                if client_id in self.connection_monitoring_tasks:
                    task = self.connection_monitoring_tasks.pop(client_id)
                    if not task.done():
                        task.cancel()
                
                # Update connection stats
                self.connection_stats["active_connections"] -= 1
                
                # Close the peer connection - without a tight timeout
                try:
                    await pc.close()
                except Exception as e:
                    logger.error(f"Error during peer connection close for {client_id}: {e}")
                
                # Clean up tracks first to stop any frame processing
                if client_id in self.tracks:
                    # No async cleanup needed for tracks
                    del self.tracks[client_id]
                
                # Remove from peer connections dictionary 
                if client_id in self.peer_connections:
                    del self.peer_connections[client_id]
                
                logger.info(f"Connection closed for client {client_id}")
                return True
            else:
                # Client connection already removed
                logger.warning(f"No connection found for client {client_id}")
                return False
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
            traceback.print_exc()
            # Force cleanup even on error
            if client_id in self.tracks:
                del self.tracks[client_id]
            if client_id in self.peer_connections:
                del self.peer_connections[client_id]
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
        """Get detailed statistics about current connections"""
        # Update the active count (for accuracy)
        self.connection_stats["active_connections"] = len(self.peer_connections)
        
        # Calculate connection age statistics
        connection_ages = []
        now = time.time()
        for client_id, pc in self.peer_connections.items():
            if hasattr(pc, '_creation_time'):
                age = now - pc._creation_time
                connection_ages.append(age)
        
        # Calculate average connection age
        avg_age = sum(connection_ages) / len(connection_ages) if connection_ages else 0
        
        # Get a count of connections in each state
        state_counts = {}
        for client_id, pc in self.peer_connections.items():
            state = pc.connectionState
            if state not in state_counts:
                state_counts[state] = 0
            state_counts[state] += 1
        
        # Build an enhanced stats object
        return {
            # Basic counts
            "connections": len(self.peer_connections),
            "active_tracks": len(self.tracks),
            "monitoring_tasks": len(self.connection_monitoring_tasks),
            "video_config": self.video_config,
            
            # Connection history
            "total_connections": self.connection_stats["total_connections"],
            "failed_connections": self.connection_stats["failed_connections"],
            "recovered_connections": self.connection_stats["recovered_connections"],
            
            # Connection health
            "avg_connection_age_seconds": round(avg_age, 1),
            "connection_states": state_counts,
            
            # Track timestamp for debugging
            "timestamp": time.time()
        }