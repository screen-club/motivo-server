import asyncio
import cv2
import time
import os
import logging
import numpy as np
import torch
from datetime import datetime
import json

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
    target_frame_duration = 1.0 / config.fps
    loop_start_time = time.monotonic()
    
    logger.info(f"Starting simulation loop (Target FPS: {config.fps}, Target Duration: {target_frame_duration:.4f}s)")
    
    while app_state.is_running:
        iter_start_time = time.monotonic()
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
            
            # Prioritize WebRTC frame generation, which is the most time-sensitive
            render_task = asyncio.create_task(render_and_process_frame(frame_count, q_percentage, last_frame_save_time))
            
            # Run pose update in parallel (less time sensitive)
            pose_task = asyncio.create_task(broadcast_pose_update(q_percentage, frame_count))
            
            frame_count += 1
            
            if terminated:
                observation, _ = app_state.env.reset()
            
            # Calculate actual duration and sleep time
            iter_end_time = time.monotonic()
            iter_duration = iter_end_time - iter_start_time
            sleep_duration = target_frame_duration - iter_duration

            # Wait for the tasks to complete
            tasks_timeout = min(sleep_duration if sleep_duration > 0 else 0.01, 0.05)  # Max 50ms
            try:
                # Prioritize render task as it's more important for video flow
                # Wait for tasks with a short timeout
                await asyncio.wait_for(render_task, timeout=tasks_timeout)
                
                # If we still have time, wait for pose update task
                remaining_time = target_frame_duration - (time.monotonic() - iter_start_time)
                if remaining_time > 0:
                    await asyncio.wait_for(pose_task, timeout=min(remaining_time, 0.01))
                    
            except asyncio.TimeoutError:
                # Tasks taking too long - create a dedicated task to monitor them
                async def monitor_pending_tasks(pending_tasks):
                    for task in pending_tasks:
                        if not task.done():
                            try:
                                await task
                            except Exception as e:
                                logger.error(f"Error in background task: {e}")
                
                pending_tasks = []
                if not render_task.done():
                    pending_tasks.append(render_task)
                if not pose_task.done():
                    pending_tasks.append(pose_task)
                    
                if pending_tasks:
                    asyncio.create_task(monitor_pending_tasks(pending_tasks))
                    logger.debug(f"Tasks taking longer than expected, moved {len(pending_tasks)} to background")

            # Log timing info periodically
            if frame_count % 60 == 0:
                # Calculate actual frame rate to check if we're keeping up with target FPS
                actual_fps = 60 / max(0.001, time.monotonic() - getattr(app_state, 'last_fps_check_time', iter_start_time - 60/config.fps))
                app_state.last_fps_check_time = time.monotonic()
                
                logger.debug(f"Frame {frame_count}: Duration={iter_duration:.4f}s, Sleep={sleep_duration:.4f}s, Actual FPS={actual_fps:.1f} (Target={config.fps})")
                
                # Track if we're consistently behind schedule
                if not hasattr(app_state, 'behind_schedule_count'):
                    app_state.behind_schedule_count = 0
                    
                if sleep_duration < 0:
                    app_state.behind_schedule_count += 1
                else:
                    app_state.behind_schedule_count = max(0, app_state.behind_schedule_count - 1)
                    
                # If consistently behind, log a warning
                if app_state.behind_schedule_count > 5:
                    logger.warning(f"Consistently behind schedule ({app_state.behind_schedule_count} frames). " +
                                   f"Target: {1/target_frame_duration:.1f} FPS, Actual: {actual_fps:.1f} FPS")

            # Sleep for the remaining time, OR sleep for 0 to yield control if behind schedule
            # Use a small minimum sleep to ensure other tasks can run
            await asyncio.sleep(max(0.001, sleep_duration))
            # else: # Optional: Log if we are falling behind
            #     # This case is now handled by sleeping for 0
            #     # logger.warning(f"Frame {frame_count}: Loop took longer ({iter_duration:.4f}s) than target ({target_frame_duration:.4f}s). No sleep.")

        except Exception as e:
            logger.error(f"Error in simulation loop: {str(e)}")
            await asyncio.sleep(1)  # Sleep longer on error
    
    loop_end_time = time.monotonic()
    total_duration = loop_end_time - loop_start_time
    actual_avg_fps = frame_count / total_duration if total_duration > 0 else 0
    logger.info(f"Simulation loop ended. Ran for {total_duration:.2f}s, {frame_count} frames. Actual avg FPS: {actual_avg_fps:.2f}")

async def broadcast_pose_update(q_percentage, frame_count: int):
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

        # Log payload size before sending
        try:
             payload_json = json.dumps(pose_data)
             payload_size = len(payload_json)
             # Log periodically or if size exceeds a threshold to avoid spam
             if frame_count % 60 == 0: # Log every 60 frames (use passed frame_count)
                  logger.debug(f"Broadcasting pose_data payload size: {payload_size} bytes")
        except Exception as e:
             logger.error(f"Error serializing pose_data for size check: {e}")
             payload_json = "{}" # Use empty dict string on error

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
                app_state.ws_manager.broadcast(pose_data), # Pass the dict, manager handles serialization
                timeout=1.5  # Increased timeout from 0.5s to 1.5s
            )
        except asyncio.TimeoutError:
            logger.warning("Broadcast operation timed out after 1.5 seconds")
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
    """Render current frame and process it for display and streaming with optimized priority"""
    try:
        frame_start_time = time.monotonic()
        
        # IMPORTANT: DON'T use threads for rendering! We need this on the main thread
        # for OpenGL/GPU context reasons
        
        # Render frame directly
        frame = app_state.env.render()
        
        # --- ADD RED DOT BEFORE DISPLAY ---
        # Draw red dot directly onto the frame if recording, *before* display
        if app_state.message_handler.video_recorder and app_state.message_handler.video_recorder.recording:
            # Frame is RGB, so red is (255, 0, 0)
            h, w = frame.shape[:2]
            radius = 10 # Adjust radius as needed
            center = (w - radius - 10, radius + 10) # Top-right corner with padding
            color = (255, 0, 0) # Red in RGB
            thickness = -1 # Filled circle
            cv2.circle(frame, center, radius, color, thickness) # Modify frame in place
        
        # Apply overlays and display the frame (now potentially with red dot)
        frame_with_overlays = app_state.display_manager.show_frame(
            frame, # Pass the potentially modified frame
            q_percentage=q_percentage,
            is_computing=app_state.message_handler.is_computing_reward
        )
        
        # Make a copy for WebRTC to avoid any potential memory issues
        frame_copy = frame_with_overlays.copy()
        
        # PRIORITY 1: Update WebRTC stream ASAP - this is the most time-sensitive task
        webrtc_updated = False
        webrtc_connections = 0
        
        try:
            # First check if we have any WebRTC connections to avoid unnecessary work
            if hasattr(app_state.webrtc_manager, 'tracks') and app_state.webrtc_manager.tracks:
                webrtc_connections = len(app_state.webrtc_manager.tracks)
                
                if webrtc_connections > 0:
                    # Don't use a timeout here to ensure the frame gets through
                    result = await app_state.webrtc_manager.broadcast_frame(frame_copy)
                    webrtc_updated = result > 0
                    
                    # Measure and log WebRTC frame processing time periodically
                    webrtc_time = time.monotonic() - frame_start_time
                    if frame_count % 300 == 0:
                        logger.debug(f"WebRTC frame processing time: {webrtc_time*1000:.1f}ms for {result} connections")
        except Exception as e:
            logger.error(f"Error in WebRTC broadcast: {e}")
        
        # PRIORITY 2: Add frame to video recorder if active (background task is fine)
        recorder_task = None
        if app_state.message_handler.video_recorder and app_state.message_handler.video_recorder.recording:
            try:
                # Schedule recording in background task
                recorder_task = asyncio.create_task(app_state.message_handler.video_recorder.add_frame(frame_with_overlays))
            except Exception as video_err:
                logger.error(f"Error scheduling frame for video recorder: {video_err}")

        # PRIORITY 3: Check for key presses (quit/save) - keep on main thread
        should_quit, should_save = app_state.display_manager.check_key()
        if should_quit:
            app_state.is_running = False
        elif should_save:
            save_current_frame(frame)
            
        # Periodically check for completed tasks and clean up
        if frame_count % 100 == 0:
            # Only track stats for active connections
            if webrtc_connections > 0:
                # Store rolling average of frame times
                if not hasattr(app_state, 'frame_time_history'):
                    app_state.frame_time_history = []
                
                frame_time = time.monotonic() - frame_start_time
                app_state.frame_time_history.append(frame_time)
                
                # Keep only last 100 samples
                if len(app_state.frame_time_history) > 100:
                    app_state.frame_time_history = app_state.frame_time_history[-100:]
                
                avg_frame_time = sum(app_state.frame_time_history) / len(app_state.frame_time_history)
                logger.debug(f"Avg frame processing time: {avg_frame_time*1000:.1f}ms, WebRTC connections: {webrtc_connections}")
    
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