import asyncio
import cv2
import time
import os
import logging
import numpy as np
import torch
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
            # Get current context - should be a tensor, not a coroutine
            current_z = app_state.message_handler.get_current_z()
            
            # Handle None case
            if current_z is None:
                # Use default z as fallback
                if hasattr(app_state.model, 'get_default_z'):
                    current_z = app_state.model.get_default_z()
                else:
                    # Create a zero tensor as fallback
                    default_shape = (1, 256)  # Common latent dimension, adjust if needed
                    current_z = torch.zeros(default_shape, device=next(app_state.model.parameters()).device)
            
            # Generate action
            try:
                # Call model.act and handle potential coroutine
                action_result = app_state.model.act(observation, current_z, mean=True)
                
                # Always await if it's a coroutine
                if asyncio.iscoroutine(action_result):
                    action = await action_result
                else:
                    action = action_result
            except Exception as e:
                logger.error(f"Error generating action: {str(e)}")
                # Create a fallback action of the right shape
                action_shape = app_state.env.action_space.shape
                action = torch.zeros(action_shape, device=next(app_state.model.parameters()).device)
            
            # Fix for coroutine issue - ensure action is a tensor and properly convert to numpy
            if isinstance(action, torch.Tensor):
                # If action is already a tensor, properly detach and convert to numpy
                action_np = action.detach().cpu().numpy() if hasattr(action, 'detach') else action.cpu().numpy()
                # Use numpy array for stepping the environment
                action_for_env = action_np.ravel()
            else:
                # If action is not a tensor (might be a coroutine or something else), log and use default
                logger.warning(f"Action is not a tensor, type: {type(action)}")
                # Create a zero action of appropriate size as fallback
                action_shape = app_state.env.action_space.shape
                action_np = np.zeros(action_shape)
                action_for_env = action_np
            
            # Handle compute_q_value
            try:
                # Call compute_q_value directly - it's not a coroutine function
                q_value = compute_q_value(app_state.model, observation, current_z, action_np)
            except Exception as e:
                logger.error(f"Error computing q_value: {str(e)}")
                q_value = 0.5  # Fallback value
                
            q_percentage = normalize_q_value(q_value)
            
            # Step the environment with the numpy action
            observation, _, terminated, truncated, _ = app_state.env.step(action_for_env)
            
            # These operations remain async
            await broadcast_pose_update(q_percentage)
            await render_and_process_frame(frame_count, q_percentage, last_frame_save_time)
            frame_count += 1
            
            if terminated:
                observation, _ = app_state.env.reset()
            
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
        
        # Check if websocket manager is properly initialized
        if not hasattr(app_state, 'ws_manager') or app_state.ws_manager is None:
            logger.warning("WebSocket manager not initialized, skipping broadcast")
            return
            
        # Check if there are any clients to broadcast to
        if not app_state.ws_manager.connected_clients:
            return
        
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
        except Exception as broadcast_error:
            logger.error(f"Error during broadcast: {broadcast_error}")
            # Try to cleanup connections on any broadcast error
            await cleanup_stale_connections()
    except Exception as e:
        logger.error(f"Error broadcasting pose data: {str(e)}")

async def cleanup_stale_connections():
    """Remove any stale WebSocket connections"""
    import websockets
    
    stale_connections = set()
    for ws in app_state.ws_manager.connected_clients:
        try:
            if hasattr(ws, 'closed') and ws.closed:
                stale_connections.add(ws)
                logger.warning("Found closed connection that wasn't properly removed")
            # Check for connection state in case 'closed' attribute isn't available
            elif not hasattr(ws, 'closed'):
                # Try to ping the connection to check if it's still alive
                try:
                    pong_waiter = await ws.ping()
                    await asyncio.wait_for(pong_waiter, timeout=0.5)
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed, Exception):
                    # Connection is not responding, mark as stale
                    stale_connections.add(ws)
                    logger.warning("Found stale connection without 'closed' attribute")
        except AttributeError:
            logger.warning("Connection missing expected attributes, marking as stale")
            stale_connections.add(ws)
        except Exception as e:
            logger.error(f"Error checking connection state: {e}")
            # If we can't determine connection state, safer to mark as stale
            stale_connections.add(ws)
    
    # Remove stale connections
    for ws in stale_connections:
        app_state.ws_manager.connected_clients.discard(ws)
        
    logger.info(f"Removed {len(stale_connections)} stale connections, {len(app_state.ws_manager.connected_clients)} remaining")

async def render_and_process_frame(frame_count, q_percentage, last_frame_save_time):
    """Render current frame and process it for display and streaming"""
    try:
        # IMPORTANT: DON'T use threads for rendering! We need this on the main thread
        # for OpenGL/GPU context reasons
        
        # Render frame directly
        frame = app_state.env.render()
        
        # Apply overlays directly
        frame_with_overlays = app_state.display_manager.show_frame(
            frame,
            q_percentage=q_percentage,
            is_computing=app_state.message_handler.is_computing_reward
        )
        
        # Make a copy for WebRTC to avoid any potential memory issues
        frame_copy = frame_with_overlays.copy()
        
        # Update WebRTC stream with proper task management - async operations
        try:
            # Create a task with a timeout to prevent stalled tasks
            webrtc_task = asyncio.create_task(
                asyncio.wait_for(
                    app_state.webrtc_manager.broadcast_frame(frame_copy),
                    timeout=0.5  # Back to 500ms timeout
                )
            )
            
            # Task management - ensure we have a place to track pending tasks
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
        
        # Check for key presses (quit/save) - KEEP THIS ON MAIN THREAD TOO
        should_quit, should_save = app_state.display_manager.check_key()
        if should_quit:
            app_state.is_running = False
        elif should_save:
            save_current_frame(frame)
    
    except Exception as e:
        logger.error(f"Error in render_and_process_frame: {str(e)}")

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