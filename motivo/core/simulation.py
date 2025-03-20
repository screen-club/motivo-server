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
from utils.frame_utils import save_frame_data, save_shared_frame
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
        if ws.closed:
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
    
    # Instead of saving frames on every render, we'll only save when explicitly requested
    # via the webserver's gemini_capture event
    
    # Update WebRTC stream with proper task management
    frame_copy = frame_with_overlays.copy()
    
    # Use a more controlled approach for creating and tracking tasks
    try:
        # Create a task with a timeout to prevent stalled tasks
        webrtc_task = asyncio.create_task(
            asyncio.wait_for(
                app_state.webrtc_manager.broadcast_frame(frame_copy),
                timeout=0.5  # 500ms timeout to prevent blocking
            )
        )
        
        # Optionally add task to a global task set for cleanup
        # This prevents tasks from lingering and causing memory leaks
        if not hasattr(app_state, 'pending_webrtc_tasks'):
            app_state.pending_webrtc_tasks = set()
        
        app_state.pending_webrtc_tasks.add(webrtc_task)
        
        # Set up cleanup callback
        def task_done(task):
            try:
                app_state.pending_webrtc_tasks.discard(task)
            except:
                pass
        
        webrtc_task.add_done_callback(task_done)
        
        # Periodically clean up completed tasks (every 100 frames)
        if frame_count % 100 == 0 and hasattr(app_state, 'pending_webrtc_tasks'):
            done_tasks = {task for task in app_state.pending_webrtc_tasks if task.done()}
            for task in done_tasks:
                app_state.pending_webrtc_tasks.discard(task)
            logger.debug(f"Cleaned up {len(done_tasks)} completed WebRTC tasks, {len(app_state.pending_webrtc_tasks)} pending")
    
    except Exception as e:
        logger.error(f"Error setting up WebRTC broadcast: {e}")
    
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