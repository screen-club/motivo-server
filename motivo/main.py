import torch
import asyncio
import websockets
import json
import cv2
from concurrent.futures import ThreadPoolExecutor
from metamotivo.fb_cpr.huggingface import FBcprModel
import os
from datetime import datetime
import numpy as np
from frame_utils import save_frame_data
from utils.smpl_utils import qpos_to_smpl, smpl_to_qpose
from pathlib import Path
import base64
from aiortc import RTCIceCandidate

from env_setup import setup_environment
from buffer_utils import download_buffer
from reward_context import compute_reward_context, compute_q_value
from task_rewards import print_model_info, list_model_body_names, print_available_rewards
from humenv import rewards as humenv_rewards
from typing import Dict, Any
from frame_utils import FrameRecorder
from cache_utils import RewardContextCache
from ws_manager import WebSocketManager
from utils.utils import normalize_q_value
from display_utils import DisplayManager
from message_handler import MessageHandler
from webrtc_manager import WebRTCManager
import traceback

# Environment variables
BACKEND_DOMAIN = os.getenv("VITE_BACKEND_DOMAIN", "localhost")
WS_PORT = os.getenv("VITE_WS_PORT", 8765)
API_PORT = os.getenv("VITE_API_PORT", 5000)
WEBSERVER_PORT = os.getenv("VITE_WEBSERVER_PORT", 5002)
VITE_WS_URL = os.getenv("VITE_WS_URL", f"ws://{BACKEND_DOMAIN}:{WS_PORT}")

def get_cached_model(model_name: str, cache_dir: str = "./storage/cache") -> FBcprModel:
    """
    Get model from cache if it exists, otherwise download and cache it.
    
    Args:
        model_name: Name of the model to load
        cache_dir: Directory to store cached models
        
    Returns:
        Loaded model instance
    """
    # Create cache directory if it doesn't exist
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    # Create model-specific cache path
    model_cache_path = cache_path / model_name
    
    if model_cache_path.exists():
        print(f"Loading model from cache: {model_cache_path}")
        model = FBcprModel.from_pretrained(str(model_cache_path))
    else:
        print(f"Downloading model {model_name} and caching to: {model_cache_path}")
        model = FBcprModel.from_pretrained(f"facebook/{model_name}")
        model.save_pretrained(str(model_cache_path))
    
    return model

# Application state
class AppState:
    def __init__(self):
        self.model = None
        self.env = None
        self.buffer_data = None
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        self.ws_manager = WebSocketManager()
        self.webrtc_manager = WebRTCManager(video_quality="high")  # Initialize without env first
        self.context_cache = None  # Initialize later when we have model, env, and buffer_data
        
        # Initialize DisplayManager in headless mode for Docker compatibility
        # Check if running in Docker/container environment
        in_container = os.path.exists('/.dockerenv') or os.environ.get('ENVIRONMENT') == 'production'
        self.display_manager = DisplayManager(headless=in_container)
        
        self.message_handler = None

    def initialize(self, model, env, buffer_data):
        self.model = model
        self.env = env
        self.buffer_data = buffer_data
        # Create cache with all required components
        self.context_cache = RewardContextCache(model=model, env=env, buffer_data=buffer_data)
        self.message_handler = MessageHandler(model, env, self.ws_manager, self.context_cache)
        self.message_handler.set_buffer_data(buffer_data)
        
        # Now that we have the environment, set it in the WebRTC manager
        self.webrtc_manager.set_environment(env)

    async def get_reward_context(self, reward_config):
        """Async wrapper for reward context computation"""
        try:
            self.message_handler.is_computing_reward = True
            print("\n=== Reward Context Computation ===")
            print("Computing... ⚙️")
            
            # Notify clients that computation started
            await self.ws_manager.broadcast({
                "type": "reward_computation",
                "status": "started",
                "timestamp": datetime.now().isoformat()
            })
            
            # Using asyncio.to_thread instead of ThreadPoolExecutor
            z = await asyncio.to_thread(
                compute_reward_context,
                reward_config,
                self.env,
                self.model,
                self.buffer_data
            )
            
            # Get the cache file path for this reward configuration
            cache_key = self.context_cache.get_cache_key(reward_config)
            cache_file = self.context_cache._get_cache_file(cache_key)
            
            # Notify clients that computation is complete
            await self.ws_manager.broadcast({
                "type": "reward_computation",
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "cache_file": str(cache_file)
            })
            
            return z
        finally:
            self.message_handler.is_computing_reward = False
            print("✅ Computation complete!")

app_state = AppState()

async def handle_websocket(websocket):
    """Handle websocket connections"""
    # Enhanced logging for connection diagnostics
    client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}" if hasattr(websocket, 'remote_address') else "Unknown"
    print(f"\n=== New WebSocket Connection Established from {client_info} ===")
    
    app_state.ws_manager.connected_clients.add(websocket)
    print(f"Total connections: {len(app_state.ws_manager.connected_clients)}")
    
    try:
        # Send initial welcome message to confirm connection is working
        try:
            welcome_msg = {
                "type": "connection_established",
                "message": "Successfully connected to WebSocket server",
                "timestamp": datetime.now().isoformat(),
                "server_info": {
                    "backend_domain": BACKEND_DOMAIN,
                    "ws_port": WS_PORT
                }
            }
            await websocket.send(json.dumps(welcome_msg))
            print(f"Sent welcome message to {client_info}")
        except Exception as e:
            print(f"Error sending welcome message: {str(e)}")
        
        async for message in websocket:
            try:
                # Log the raw message for debugging
                print(f"Received message from {client_info}: {message[:100]}...")
                
                data = json.loads(message)
                
                # Handle WebRTC signaling
                if data.get("type") == "webrtc_offer":
                    client_id = data.get("client_id")
                    sdp = data.get("sdp")
                    
                    if client_id and sdp:
                        # Unconditional WebRTC logging - always log regardless of environment
                        print(f"[WEBRTC-DIAG] Offer received from client {client_id}")
                        codec_lines = [line for line in sdp.split('\n') if 'a=rtpmap:' in line]
                        print(f"[WEBRTC-DIAG] Client codecs: {codec_lines}")
                        
                        # Check if there's a video section in the SDP
                        video_section = "m=video" in sdp
                        print(f"[WEBRTC-DIAG] SDP contains video section: {video_section}")
                        
                        answer = await app_state.webrtc_manager.handle_offer(client_id, sdp)
                        
                        # Send the answer back
                        await websocket.send(json.dumps({
                            "type": "webrtc_answer",
                            "sdp": answer["sdp"],
                            "sdpType": answer["type"],
                            "client_id": client_id,
                            "timestamp": datetime.now().isoformat()
                        }))
                        
                        # Always log answer details
                        print(f"[WEBRTC-DIAG] Answer sent to client {client_id}, type: {answer['type']}")
                        server_codec_lines = [line for line in answer["sdp"].split('\n') if 'a=rtpmap:' in line]
                        print(f"[WEBRTC-DIAG] Server codecs: {server_codec_lines}")
                    continue
                
                # Handle new ping messages from client
                if data.get("type") == "ping":
                    print(f"Received ping from {client_info}")
                    # Respond with pong
                    await websocket.send(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }))
                    continue
                
                # Handle video quality change requests
                if data.get("type") == "set_video_quality":
                    client_id = data.get("client_id")
                    quality = data.get("quality")
                    
                    if quality and quality in ["low", "medium", "high", "hd"]:
                        # Try low quality in Docker to reduce encoding demands
                        if os.environ.get("ENVIRONMENT") == "production" and quality != "low":
                            print(f"In Docker: Received request for {quality} quality, consider using 'low' if video fails")
                            
                        success = app_state.webrtc_manager.set_video_quality(quality)
                        
                        # Send confirmation
                        await websocket.send(json.dumps({
                            "type": "video_quality_changed",
                            "quality": quality,
                            "success": success,
                            "client_id": client_id,
                            "timestamp": datetime.now().isoformat()
                        }))
                    continue
                
                # Handle ICE candidates
                if data.get("type") == "ice_candidate":
                    client_id = data.get("client_id")
                    candidate_dict = data.get("candidate")
                    
                    if client_id and candidate_dict and client_id in app_state.webrtc_manager.peer_connections:
                        pc = app_state.webrtc_manager.peer_connections[client_id]
                        
                        try:
                            # Parse ICE candidate string manually
                            candidate_str = candidate_dict.get("candidate", "")
                            
                            # Always log ICE candidate info
                            candidate_type = "unknown"
                            if "typ " in candidate_str:
                                candidate_type = candidate_str.split("typ ")[1].split()[0]
                            print(f"[WEBRTC-DIAG] ICE candidate from client {client_id}: type={candidate_type}")
                            
                            # Extract IP address for network debugging if present
                            if len(candidate_str.split()) >= 5:
                                ip = candidate_str.split()[4]
                                print(f"[WEBRTC-DIAG] ICE candidate IP: {ip}")
                            
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
                                
                                # Add the candidate to the peer connection
                                await pc.addIceCandidate(ice_candidate)
                                print(f"Added ICE candidate for client {client_id}")
                            else:
                                print(f"Invalid ICE candidate format: {candidate_str}")
                        except Exception as e:
                            print(f"Error adding ICE candidate: {str(e)}")
                            traceback.print_exc()
                    continue
                
                # Handle other messages
                await app_state.message_handler.handle_message(websocket, message)
                
            except json.JSONDecodeError:
                await app_state.message_handler.handle_message(websocket, message)
                
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        app_state.ws_manager.connected_clients.discard(websocket)
        print(f"Client disconnected. Total connections: {len(app_state.ws_manager.connected_clients)}")

async def broadcast_pose(pose_data):
    """Broadcast pose data to all connected clients"""
    await app_state.ws_manager.broadcast(pose_data)

async def run_simulation():
    """Continuous simulation loop"""
    observation, _ = app_state.env.reset()
    
    # Add counter for frame diagnostics
    frame_count = 0
    black_frame_count = 0
    
    while True:
        # Get action and step environment
        #print(f"Running simulation at frame {frame_count}")
        current_z = app_state.message_handler.get_current_z()
        action = app_state.model.act(observation, current_z, mean=True)
        q_value = compute_q_value(app_state.model, observation, current_z, action)
        q_percentage = normalize_q_value(q_value)
        observation, _, terminated, truncated, _ = app_state.env.step(action.cpu().numpy().ravel())
        
        # Broadcast pose data using WebSocketManager with timeout protection
        try:
            qpos = app_state.env.unwrapped.data.qpos
            pose, trans, positions, position_names = qpos_to_smpl(qpos, app_state.env.unwrapped.model)
            
            # Get cache file for current z if available
            current_z = app_state.message_handler.get_current_z()
            cache_file = None
            if app_state.message_handler.current_reward_config is not None:
                cache_key = app_state.context_cache.get_cache_key(app_state.message_handler.current_reward_config)
                cache_file = app_state.context_cache._get_cache_file(cache_key)
            
            pose_data = {
                "type": "smpl_update",
                "pose": pose.tolist(),
                "trans": trans.tolist(),
                "positions": [pos.tolist() for pos in positions],
                "qpos": qpos.tolist(),
                "timestamp": datetime.now().isoformat(),
                "position_names": position_names,
                "cache_file": str(cache_file) if cache_file else None
            }
            
            #print(f"Broadcasting pose data to {len(app_state.ws_manager.connected_clients)} clients")
            
            # Add timeout protection to prevent blocking indefinitely
            try:
                # Use asyncio.wait_for to add a timeout
                await asyncio.wait_for(
                    app_state.ws_manager.broadcast(pose_data),
                    timeout=0.5  # 500ms timeout, adjust as needed
                )
                print(f"Successfully broadcast pose data")
            except asyncio.TimeoutError:
                print(f"WARNING: Broadcast operation timed out after 0.5 seconds")
                # Check for and clean up any dead connections that might be causing the timeout
                stale_connections = set()
                for ws in app_state.ws_manager.connected_clients:
                    if ws.state == websockets.ConnectionState.CLOSED:
                        stale_connections.add(ws)
                        print(f"Found closed connection that wasn't properly removed")
                
                # Remove stale connections
                for ws in stale_connections:
                    app_state.ws_manager.connected_clients.discard(ws)
                    
                print(f"Removed {len(stale_connections)} stale connections, {len(app_state.ws_manager.connected_clients)} remaining")
        except Exception as e:
            print(f"Error broadcasting pose data: {str(e)}")
            traceback.print_exc()
        
        # Render and display frame
        frame = app_state.env.render()
        frame_count += 1
        
        # Log frame information periodically or for early frames
        if frame_count % 100 == 0 or frame_count < 5:
            # Always log frame information
            print(f"[FRAME-DIAG] Frame {frame_count} - shape: {frame.shape}, dtype: {frame.dtype}, min: {frame.min()}, max: {frame.max()}")

            # Check if frame is mostly black - potential rendering issue
            if frame.size > 0 and frame.max() < 20:  # very dark frame
                black_frame_count += 1
                print(f"[FRAME-DIAG] WARNING: Frame {frame_count} is mostly black/dark. Black frame count: {black_frame_count}")
                
                # Save diagnostic image unconditionally
                try:
                    os.makedirs("/tmp/webrtc_diagnostic", exist_ok=True)
                    cv2.imwrite(f"/tmp/webrtc_diagnostic/black_frame_{frame_count}.png", frame)
                    print(f"[FRAME-DIAG] Saved black frame to /tmp/webrtc_diagnostic/black_frame_{frame_count}.png")
                except Exception as e:
                    print(f"[FRAME-DIAG] Error saving diagnostic frame: {str(e)}")
        
        # First apply overlays using the display manager
        # But store the result for WebRTC instead of just displaying it
        frame_with_overlays = app_state.display_manager.show_frame(
            frame,
            q_percentage=q_percentage,
            is_computing=app_state.message_handler.is_computing_reward
        )
        
        # Now send the frame WITH overlays to WebRTC - log every 50 frames
        if frame_count % 50 == 0:
            print(f"[WEBRTC-DIAG] Sending frame {frame_count} to WebRTC - shape: {frame_with_overlays.shape}")
            # Log active connections
            active_connections = sum(1 for pc in app_state.webrtc_manager.peer_connections.values() 
                                  if pc.connectionState == "connected")
            print(f"[WEBRTC-DIAG] Active WebRTC connections: {active_connections}/{len(app_state.webrtc_manager.peer_connections)}")
        
        app_state.webrtc_manager.update_frame(frame_with_overlays)
        
        # The display_manager.show_frame function already showed the frame in the local window,
        # so we don't need to call it again
        
        # Send a ping message to notify clients that a new frame is available
        frame_ping = {
            "type": "video_frame_ping",
            "timestamp": datetime.now().isoformat(),
            "available": True
        }
        
        # Add timeout protection here too
        try:
            await asyncio.wait_for(
                app_state.ws_manager.broadcast(frame_ping),
                timeout=0.5  # 500ms timeout
            )
        except asyncio.TimeoutError:
            print(f"WARNING: Frame ping broadcast timed out")
        except Exception as e:
            print(f"Error broadcasting frame ping: {str(e)}")
        
        # Check for key presses
        should_quit, should_save = app_state.display_manager.check_key()
        if should_quit:
            break
        elif should_save:
            try:
                env_data = app_state.env.unwrapped.data
                save_frame_data(
                    frame=frame,
                    qpos=env_data.qpos.copy(),
                    qvel=env_data.qvel.copy(),
                    env=app_state.env
                )
                print("Frame saved! 📸")
            except Exception as e:
                print("Error during frame save:", str(e))
        
        if terminated:
            observation, _ = app_state.env.reset()
        
        await asyncio.sleep(1/60)  # 60 FPS target

async def main():
    """Main function"""
    try:
        # Device selection with CUDA support
        if torch.cuda.is_available():
            device = "cuda"
            torch.backends.cudnn.benchmark = True
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        print(f"Using device: {device}")
        
        print("Loading model and environment...")
        model_name = "metamotivo-M-1"
        model = get_cached_model(model_name)
        model.to(device)
        model.eval()
        
        env = setup_environment(device)
        buffer_data = download_buffer(model_name=model_name)
        
        # Initialize application state
        app_state.initialize(model, env, buffer_data)
        
        # Get default context from cache or compute if needed
        default_config = {
            'rewards': [
                { 'name': 'move-ego', 'move_speed': 0.0, 'stand_height': 1.4 }
            ],
            'weights': [1.0]
        }
        
        # Try to get from cache first
        cache_key = app_state.context_cache.get_cache_key(default_config)
        default_z, _ = app_state.context_cache._get_cached_context_impl(cache_key)
        
        if default_z is None:
            print("\nDefault context not found in cache, computing...")
            default_z = await app_state.get_reward_context(default_config)
        else:
            print("\nUsing cached default context")
            
        if default_z is None:
            raise RuntimeError("Failed to compute initial context")
            
        app_state.message_handler.set_default_z(default_z)
        
        print("\nStarting WebSocket server and simulation...")
        server = await websockets.serve(handle_websocket, "0.0.0.0", WS_PORT)
        print(f"WebSocket server started at ws://{BACKEND_DOMAIN}:{WS_PORT}")
        
        await asyncio.gather(
            server.wait_closed(),
            run_simulation()
        )
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Close all WebRTC connections
        await app_state.webrtc_manager.close_all_connections()
        app_state.display_manager.cleanup()
        app_state.thread_pool.shutdown()

if __name__ == "__main__":
    asyncio.run(main())