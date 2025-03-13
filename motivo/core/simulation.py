import asyncio
import cv2
import time
import os
import logging
import numpy as np
from datetime import datetime

from core.config import config
from core.state import app_state
from utils.smpl_utils import qpos_to_smpl
from utils.frame_utils import save_frame_data
from utils.utils import normalize_q_value
from rewards.reward_context import compute_q_value

logger = logging.getLogger('simulation')

async def run_simulation_loop():
    """Run the continuous simulation loop"""
    if not app_state.is_initialized:
        raise RuntimeError("App state not initialized")
    
    observation, _ = app_state.env.reset()
    frame_count = 0
    last_frame_save_time = 0
    app_state.is_running = True
    
    logger.info("Starting simulation loop")
    
    while app_state.is_running:
        try:
            # Get current context from message handler
            current_z = app_state.message_handler.get_current_z()
            
            # Generate action based on current context and observation
            action = app_state.model.act(observation, current_z, mean=True)
            q_value = compute_q_value(app_state.model, observation, current_z, action)
            q_percentage = normalize_q_value(q_value)
            
            # Step the environment with the action
            observation, _, terminated, truncated, _ = app_state.env.step(action.cpu().numpy().ravel())
            
            # Handle pose updates and broadcasting
            await broadcast_pose_update(q_percentage)
            
            # Handle frame rendering and display
            await render_and_process_frame(frame_count, q_percentage, last_frame_save_time)
            frame_count += 1
            
            # Check for termination
            if terminated:
                observation, _ = app_state.env.reset()
            
            # Maintain frame rate
            await asyncio.sleep(1/config.fps)
        except Exception as e:
            logger.error(f"Error in simulation loop: {str(e)}")
            await asyncio.sleep(1)  # Sleep longer on error
    
    logger.info("Simulation loop ended")

async def broadcast_pose_update(q_percentage):
    """Get current pose data and broadcast to clients"""
    try:
        # Get pose data from environment
        qpos = app_state.env.unwrapped.data.qpos
        pose, trans, positions, position_names = qpos_to_smpl(qpos, app_state.env.unwrapped.model)
        
        # Get cache file for current context if available
        cache_file = None
        if app_state.message_handler.current_reward_config is not None:
            cache_key = app_state.context_cache.get_cache_key(app_state.message_handler.current_reward_config)
            cache_file = app_state.context_cache._get_cache_file(cache_key)
        
        # Prepare pose data for broadcast
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
        
        # Broadcast with timeout protection
        try:
            await asyncio.wait_for(
                app_state.ws_manager.broadcast(pose_data),
                timeout=0.5  # 500ms timeout
            )
        except asyncio.TimeoutError:
            logger.warning("Broadcast operation timed out after 0.5 seconds")
            # Handle stale connections
            await cleanup_stale_connections()
    except Exception as e:
        logger.error(f"Error broadcasting pose data: {str(e)}")

async def cleanup_stale_connections():
    """Remove any stale WebSocket connections"""
    import websockets
    
    stale_connections = set()
    for ws in app_state.ws_manager.connected_clients:
        if ws.state == websockets.ConnectionState.CLOSED:
            stale_connections.add(ws)
            logger.warning("Found closed connection that wasn't properly removed")
    
    # Remove stale connections
    for ws in stale_connections:
        app_state.ws_manager.connected_clients.discard(ws)
        
    logger.info(f"Removed {len(stale_connections)} stale connections, {len(app_state.ws_manager.connected_clients)} remaining")

async def render_and_process_frame(frame_count, q_percentage, last_frame_save_time):
    """Render current frame and process it for display and streaming"""
    # Render frame
    frame = app_state.env.render()
    
    # Apply overlays
    frame_with_overlays = app_state.display_manager.show_frame(
        frame,
        q_percentage=q_percentage,
        is_computing=app_state.message_handler.is_computing_reward
    )
    
    # Save frame for external services (like Gemini) periodically
    current_time = time.time()
    if current_time - last_frame_save_time >= 1.0:
        try:
            # Convert from RGB to BGR for OpenCV
            save_frame = cv2.cvtColor(frame_with_overlays.copy(), cv2.COLOR_RGB2BGR)
            cv2.imwrite(config.gemini_frame_path, save_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            # Also save a timestamp file to track when the frame was saved
            with open(os.path.join(config.shared_frames_dir, 'timestamp.txt'), 'w') as f:
                f.write(str(current_time))
            last_frame_save_time = current_time
        except Exception as e:
            logger.error(f"Error saving frame: {str(e)}")
    
    # Update WebRTC stream - direct asyncio call since broadcast_frame is a coroutine
    frame_copy = frame_with_overlays.copy()
    # Create a task for broadcasting but don't wait for it to complete
    asyncio.create_task(app_state.webrtc_manager.broadcast_frame(frame_copy))
    
    # Check for key presses (quit/save)
    should_quit, should_save = app_state.display_manager.check_key()
    if should_quit:
        app_state.is_running = False
    elif should_save:
        save_current_frame(frame)

def save_current_frame(frame):
    """Save the current frame data"""
    try:
        env_data = app_state.env.unwrapped.data
        save_frame_data(
            frame=frame,
            qpos=env_data.qpos.copy(),
            qvel=env_data.qvel.copy(),
            env=app_state.env
        )
        logger.info("Frame saved! 📸")
    except Exception as e:
        logger.error(f"Error during frame save: {str(e)}")