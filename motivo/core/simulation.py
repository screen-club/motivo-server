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
            # Get current context from message handler - handle possible coroutine
            current_z = app_state.message_handler.get_current_z()
            
            # If current_z is a coroutine, await it
            if asyncio.iscoroutine(current_z):
                logger.info("current_z is a coroutine, awaiting it")
                current_z = await current_z
            
            # Generate action and compute q-value - handle potential coroutines
            try:
                # Detailed tracing for debugging the coroutine issue
                logger.info(f"About to call model.act() - is coroutine function: {asyncio.iscoroutinefunction(app_state.model.act)}")
                
                # First check if act returns a coroutine
                import traceback
                try:
                    action = app_state.model.act(observation, current_z, mean=True)
                    logger.info(f"model.act() returned type: {type(action)}")
                    
                    # If action is a coroutine, await it
                    if asyncio.iscoroutine(action):
                        logger.info("Model.act returned a coroutine, awaiting it")
                        action = await action
                        logger.info(f"After awaiting, action is now type: {type(action)}")
                except Exception as e:
                    logger.error(f"Error in model.act(): {str(e)}")
                    traceback.print_exc()
                    raise
            except Exception as e:
                logger.error(f"Error generating action: {str(e)}")
                traceback.print_exc()
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
            
            # Handle compute_q_value potentially being a coroutine
            try:
                logger.info(f"About to call compute_q_value() - is coroutine function: {asyncio.iscoroutinefunction(compute_q_value)}")
                
                if asyncio.iscoroutinefunction(compute_q_value):
                    logger.info("compute_q_value is a coroutine function, awaiting it")
                    q_value = await compute_q_value(app_state.model, observation, current_z, action_np)
                    logger.info(f"After awaiting compute_q_value, got result type: {type(q_value)}")
                else:
                    logger.info("compute_q_value is a regular function, calling directly")
                    try:
                        result = compute_q_value(app_state.model, observation, current_z, action_np)
                        logger.info(f"compute_q_value() returned type: {type(result)}")
                        
                        if asyncio.iscoroutine(result):
                            logger.info("compute_q_value returned a coroutine, awaiting it")
                            q_value = await result
                            logger.info(f"After awaiting compute_q_value result, got type: {type(q_value)}")
                        else:
                            q_value = result
                    except Exception as e:
                        logger.error(f"Error during compute_q_value call: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        raise
            except Exception as e:
                logger.error(f"Error computing q_value: {str(e)}")
                import traceback
                traceback.print_exc()
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