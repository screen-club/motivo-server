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
        self.display_manager = DisplayManager()
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
    print("\n=== New WebSocket Connection Established ===")
    app_state.ws_manager.connected_clients.add(websocket)
    print(f"Total connections: {len(app_state.ws_manager.connected_clients)}")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle WebRTC signaling
                if data.get("type") == "webrtc_offer":
                    client_id = data.get("client_id")
                    sdp = data.get("sdp")
                    
                    if client_id and sdp:
                        answer = await app_state.webrtc_manager.handle_offer(client_id, sdp)
                        
                        # Send the answer back
                        await websocket.send(json.dumps({
                            "type": "webrtc_answer",
                            "sdp": answer["sdp"],
                            "sdpType": answer["type"],
                            "client_id": client_id,
                            "timestamp": datetime.now().isoformat()
                        }))
                    continue
                
                # Handle video quality change requests
                if data.get("type") == "set_video_quality":
                    client_id = data.get("client_id")
                    quality = data.get("quality")
                    
                    if quality and quality in ["low", "medium", "high", "hd"]:
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
    
    while True:
        # Get action and step environment
        current_z = app_state.message_handler.get_current_z()
        action = app_state.model.act(observation, current_z, mean=True)
        q_value = compute_q_value(app_state.model, observation, current_z, action)
        q_percentage = normalize_q_value(q_value)
        observation, _, terminated, truncated, _ = app_state.env.step(action.cpu().numpy().ravel())
        
        # Broadcast pose data using WebSocketManager
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
            
            await app_state.ws_manager.broadcast(pose_data)
            
        except Exception as e:
            print(f"Error broadcasting pose data: {str(e)}")
            traceback.print_exc()
        
        # Render and display frame
        frame = app_state.env.render()
        
        # Debug info to verify format - will print for first few frames
        if app_state.env.unwrapped.data.time < 2.0:  # Only during first 2 seconds
            print(f"Frame shape: {frame.shape}, dtype: {frame.dtype}, min: {frame.min()}, max: {frame.max()}")
        
        # First apply overlays using the display manager
        # But store the result for WebRTC instead of just displaying it
        frame_with_overlays = app_state.display_manager.show_frame(
            frame,
            q_percentage=q_percentage,
            is_computing=app_state.message_handler.is_computing_reward
        )
        
        # Now send the frame WITH overlays to WebRTC
        app_state.webrtc_manager.update_frame(frame_with_overlays)
        
        # The display_manager.show_frame function already showed the frame in the local window,
        # so we don't need to call it again
        
        # Send a ping message to notify clients that a new frame is available
        frame_ping = {
            "type": "video_frame_ping",
            "timestamp": datetime.now().isoformat(),
            "available": True
        }
        
        await app_state.ws_manager.broadcast(frame_ping)
        
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