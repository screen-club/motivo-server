import json
import cv2
import numpy as np
import torch
import os
import traceback
import asyncio
import logging
import websockets
import inspect
import traceback
import atexit
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import concurrent.futures
import time

from core.config import config
from utils.frame_utils import FrameRecorder, save_shared_frame
from rewards.reward_context import compute_reward_context

logger = logging.getLogger('message_handler')

# This will be set up after the MessageHandler class is defined
_cleanup_function = None

class MessageHandler:
    """Handles incoming WebSocket messages and routes them to appropriate handlers"""
    
    # Class variable to track instances for cleanup
    _instances = []
    
    def __init__(self, model, env, ws_manager, context_cache):
        # Core components
        self.model = model
        self.env = env
        self.ws_manager = ws_manager
        self.context_cache = context_cache
        self.buffer_data = None  # Will be set by AppState
        
        # State tracking
        self.current_z = None
        self.active_rewards = None
        self.active_poses = None
        self.current_reward_config = None
        self.is_computing_reward = False
        self.default_z = None
        self.frame_recorder = None
        self.computation_status = None
        self.last_computation_id = None
        
        # Environment variables from config
        self.backend_domain = config.backend_domain
        self.webserver_port = config.webserver_port
        self.ws_port = config.ws_port
        self.api_port = config.api_port

        # Set up command handlers map
        self.command_handlers = {
            "mix_pose_reward": self.handle_mix_pose_reward,
            "debug_model_info": self.handle_debug_model_info,
            "request_reward": self.handle_request_reward,
            "clean_rewards": self.handle_clean_rewards,
            "update_parameters": self.handle_update_parameters,
            "load_pose_smpl": self.handle_load_pose_smpl,
            "start_recording": self.handle_start_recording,
            "stop_recording": self.handle_stop_recording,
            "load_pose": self.handle_load_pose,
            "clear_active_rewards": self.handle_clear_active_rewards,
            "update_reward": self.handle_update_reward,
            "get_current_context": self.handle_get_current_context,
            "load_npz_context": self.handle_load_npz_context,
            "capture_frame": self.handle_capture_frame,
            "make_snapshot": self.handle_make_snapshot,
            "get_target_positions": self.handle_get_target_positions,
        }
        
        # We'll use the default executor for running tasks, so no need for custom thread pools
        
        # Add this instance to the class tracking list for cleanup
        MessageHandler._instances.append(self)
        
        logger.info("Message handler initialized")
        
    def __del__(self):
        """Clean up resources when this instance is garbage collected"""
        # Remove from instances list
        if self in MessageHandler._instances:
            MessageHandler._instances.remove(self)
            
    @classmethod
    def cleanup_all(cls):
        """Class method to clean up all instances' resources"""
        logger.info(f"Cleaning up {len(cls._instances)} MessageHandler instances")
        # Clear instances list
        cls._instances.clear()

    def set_buffer_data(self, buffer_data):
        """Set the buffer data needed for reward computation"""
        self.buffer_data = buffer_data
        logger.info("Buffer data set in message handler")

    def get_reward_context(self, reward_config):
        """
        Start computing reward context in background and return immediately.
        
        IMPORTANT: This maintains the current context while computing in background.
        The current_z value will be updated only when computation completes.
        """
        # Set the computing flag to show appropriate UI state
        self.is_computing_reward = True
        
        # Get fallback context to use in case of errors (not for immediate return)
        if hasattr(self.model, 'get_default_z'):
            fallback_context = self.model.get_default_z()
        elif hasattr(self, 'default_z'):
            fallback_context = self.default_z
        else:
            # Create a fallback tensor of appropriate shape
            latent_dim = 256  # default latent dimension
            fallback_context = torch.zeros((1, latent_dim), device=next(self.model.parameters()).device)
        
        # Store computation start info but don't broadcast to prevent feedback loops
        try:
            # Create a unique message_id for tracking
            message_id = f"compute_start_{int(time.time() * 1000)}"
            
            # Store the message ID to correlate start/complete messages
            self.last_computation_id = message_id
            
            # Create task to send status update only to originating client (if available)
            if hasattr(self, 'last_websocket') and self.last_websocket:
                self.computation_status = {
                    "type": "reward_computation_status",
                    "status": "started",
                    "message_id": message_id,
                    "timestamp": datetime.now().isoformat()
                }
            logger.debug(f"Created computation status with message_id: {message_id}")
        except Exception as e:
            logger.error(f"Error creating computation start status: {str(e)}")
        
        # Start background task to compute actual context
        asyncio.create_task(self._compute_reward_context_background(reward_config, fallback_context))
        
        # Return the CURRENT context (or fallback if current is None), so we don't disrupt the experience
        # while computing the new context in the background
        if self.current_z is None:
            return fallback_context
        else:
            return self.current_z
    
    async def _compute_reward_context_background(self, reward_config, fallback_context):
        """Background task to compute reward context and update state when done"""
        try:
            # Run the actual computation in a thread to avoid blocking asyncio loop
            loop = asyncio.get_running_loop()
            z = await loop.run_in_executor(
                None,  # Use default executor
                compute_reward_context,
                reward_config,
                self.env,
                self.model,
                self.buffer_data
            )
            
            # If computation failed, use the fallback
            if z is None:
                logger.warning("Computation returned None, using fallback context")
                z = fallback_context
                
            # Update the current_z with real computed value
            self.current_z = z
            
            # Instead of broadcasting to all clients, use the same message ID prefix from start
            # This avoids creating a feedback loop
            try:
                # Create a completion message ID correlated with the start message
                message_id = getattr(self, 'last_computation_id', None)
                if not message_id:
                    message_id = f"compute_complete_{int(time.time() * 1000)}"
                else:
                    message_id = message_id.replace('start', 'complete')
                
                # Send status only to clients that explicitly request status updates
                # This is done via the handle_debug_model_info requests
                logger.debug(f"Computation completed with message_id: {message_id}")
                
                # We no longer broadcast completion status to all clients
                # Instead, clients can request status via debug_model_info
                self.computation_status = {
                    "status": "completed",
                    "message_id": message_id,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as status_error:
                logger.error(f"Error updating computation completion status: {str(status_error)}")
            
        except Exception as e:
            logger.error(f"Error in background computation: {str(e)}")
            # On error, we DON'T change the current context - keep whatever was there
            # But if current_z is None for some reason, use the fallback
            if self.current_z is None:
                logger.warning("Current context is None after error, using fallback")
                self.current_z = fallback_context
            
            # Broadcast error status
            try:
                message_id = f"compute_error_{int(time.time() * 1000)}"
                await self.ws_manager.broadcast({
                    "type": "reward_computation_status",
                    "status": "error",
                    "error": str(e),
                    "message_id": message_id,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as broadcast_error:
                logger.error(f"Error broadcasting computation error: {str(broadcast_error)}")
        finally:
            # Always reset computing flag when done
            self.is_computing_reward = False

    async def handle_message(self, websocket, message: str) -> None:
        """Main message handler that routes to specific command handlers"""
        try:
            data = json.loads(message)
            message_type = data.get("type", "")
            
            # Log message type unless it's debug_model_info
            #if message_type != "debug_model_info":
                #logger.info(f"Handling message of type: {message_type}")
            
            # Get the appropriate handler for this message type
            handler = self.command_handlers.get(message_type)
            if handler:
                try:
                    await handler(websocket, data)
                except websockets.exceptions.ConnectionClosedError as e:
                    logger.error(f"WebSocket connection closed while handling {message_type}: {str(e)}")
                    # No need to send response as connection is closed
                except Exception as e:
                    logger.error(f"Error in handler for {message_type}: {str(e)}")
                    traceback.print_exc()
                    # Try to send error response if connection is still open
                    try:
                        await websocket.send(json.dumps({
                            "type": f"{message_type}_error",
                            "error": str(e),
                            "timestamp": datetime.now().isoformat()
                        }))
                    except:
                        pass
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON message received")
            try:
                await websocket.send(json.dumps({"error": "Invalid JSON"}))
            except:
                pass
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            traceback.print_exc()

    async def handle_start_recording(self, websocket, data: Dict[str, Any]) -> None:
        """Start recording frames"""
        self.frame_recorder = FrameRecorder()
        self.frame_recorder.recording = True
        response = {
            "type": "recording_status",
            "status": "started",
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(response))

    async def handle_stop_recording(self, websocket, data: Dict[str, Any]) -> None:
        """Stop recording and save frames"""
        if self.frame_recorder and self.frame_recorder.recording:
            try:
                
                # Create a unique filename for the zip
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                zip_filename = f"recording_{timestamp}.zip"
                
                # Use downloads dir from config
                from core.config import config
                zip_path = os.path.join(config.downloads_dir, zip_filename)
                
                
                # Save the recording and get the zip path
                self.frame_recorder.end_record(zip_path)
                
                # Create download URL using WEBSERVER_PORT
                download_url = f"http://{self.backend_domain}:{self.webserver_port}/downloads/{zip_filename}"
                logger.info(f"Download URL created: {download_url}")
                
                response = {
                    "type": "recording_status",
                    "status": "stopped",
                    "downloadUrl": download_url,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(response))
                self.frame_recorder = None
            except Exception as e:
                logger.error(f"Error stopping recording: {str(e)}")
                traceback.print_exc()
                
                error_response = {
                    "type": "recording_status",
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(error_response))

    async def handle_load_pose(self, websocket, data: Dict[str, Any]) -> None:
        """Load pose configuration from qpos data"""
   
        try:
            goal_qpos = np.array(data.get("pose", []))
            
            if len(goal_qpos) != 76:  # Expect 76 values for qpos
                raise ValueError(f"Invalid pose length: {len(goal_qpos)}, expected 76")
            
            # Save current physics state
            current_qpos = self.env.unwrapped.data.qpos.copy()
            current_qvel = self.env.unwrapped.data.qvel.copy()
            
            # Temporarily set physics to get the goal observation
            logger.info("Setting physics temporarily...")
            self.env.unwrapped.set_physics(
                qpos=goal_qpos,  # Use all 76 values for qpos
                qvel=np.zeros(75)  # Use 75 zeros for qvel
            )
            
            logger.info("Getting observation...")
            goal_obs = torch.tensor(
                self.env.unwrapped.get_obs()["proprio"].reshape(1, -1),
                device=self.model.cfg.device,
                dtype=torch.float32
            )
            logger.info(f"Observation shape: {goal_obs.shape}")
            
            # Restore original physics state (without reset)
            logger.info("Restoring original physics state...")
            self.env.unwrapped.set_physics(
                qpos=current_qpos,
                qvel=current_qvel
            )
            
            # Use goal inference to get context
            inference_type = data.get("inference_type", "goal")
            logger.info(f"Using inference type: {inference_type}")
            
            # Execute inference based on type
            try:
                # Get inference result and await if needed
                if inference_type == "goal":
                    result = self.model.goal_inference(next_obs=goal_obs)
                elif inference_type == "tracking":
                    result = self.model.tracking_inference(next_obs=goal_obs)
                else:
                    # If unsupported type, default to goal inference
                    logger.warning(f"Unsupported inference type '{inference_type}', defaulting to goal inference")
                    result = self.model.goal_inference(next_obs=goal_obs)
                
                # Await if it's a coroutine
                if asyncio.iscoroutine(result):
                    z = await result
                else:
                    z = result
                
                # Update current context
                self.current_z = z
                
            except Exception as e:
                logger.error(f"Error in inference: {str(e)}")
                # Use default z if available
                if hasattr(self, 'default_z'):
                    self.current_z = self.default_z
                else:
                    raise
            
            # Update active poses
            self.active_poses = {
                "type": "qpos",
                "qpos": goal_qpos.tolist(),
                "inference_type": inference_type
            }
            
            logger.info("Context updated successfully")
            
            # Get cache file path if we have a current reward config
            cache_file = None
            if self.current_reward_config:
                cache_key = self.context_cache.get_cache_key(self.current_reward_config)
                cache_file = self.context_cache._get_cache_file(cache_key)
            
            response = {
                "type": "pose_loaded",
                "status": "success",
                "inference_type": inference_type,
                "active_poses": self.active_poses,
                "timestamp": datetime.now().isoformat(),
                "cache_file": str(cache_file) if cache_file else None
            }
            await websocket.send(json.dumps(response))
            logger.info("Success response sent")
            
        except Exception as e:
            error_msg = f"Error loading pose: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            
            response = {
                "type": "pose_loaded",
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))

    async def handle_clear_active_rewards(self, websocket, data: Dict[str, Any]) -> None:
        """Clear all active rewards and return to default context"""
        logger.info("Clearing active rewards...")
        
        # Check if we should preserve the environment Z context
        preserve_z = data.get('preserve_z', False)
        
        self.active_rewards = None
        self.current_reward_config = None  # Clear current reward config
        self.active_poses = None  # Also clear active poses
        
        if not preserve_z:
            # Only reset the z context if we're not preserving it
            logger.info("Resetting environment context to default")
            self.current_z = self.default_z
        else:
            logger.info("Preserving environment Z context while clearing active rewards")
            
        logger.info("Active rewards cleared ✅")
        
        # Extract or generate a message ID
        message_id = data.get("message_id", f"clear_rewards_{int(time.time() * 1000)}")
        
        response = {
            "type": "rewards_cleared",
            "status": "success",
            "preserve_z": preserve_z,
            "message_id": message_id,
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(response))

    async def handle_update_reward(self, websocket, data: Dict[str, Any]) -> None:
        """Update parameters for a specific reward"""
        try:
            reward_index = data.get("index")
            new_parameters = data.get("parameters")
            
            logger.info(f"Processing reward update for index {reward_index}")
            logger.debug(f"New parameters: {json.dumps(new_parameters, indent=2)}")
            
            if self.active_rewards and 'rewards' in self.active_rewards:
                # Convert string numbers to float for numeric parameters
                for key, value in new_parameters.items():
                    try:
                        if isinstance(value, (list, tuple)):
                            logger.debug(f"Converting sequence {key}: {value} to float")
                            new_parameters[key] = float(value[0])
                        elif isinstance(value, str):
                            logger.debug(f"Converting string {key}: {value} to float")
                            new_parameters[key] = float(value)
                        elif isinstance(value, bool):
                            logger.debug(f"Keeping boolean {key}: {value}")
                            continue
                        else:
                            logger.debug(f"Converting {key}: {value} ({type(value)}) to float")
                            new_parameters[key] = float(value)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not convert {key}={value}: {str(e)}")
                        continue
                
                # Update the specific reward's parameters
                self.active_rewards['rewards'][reward_index].update(new_parameters)
                self.current_reward_config = self.active_rewards  # Update current reward config
                
                logger.info("Recomputing context...")
                # get_reward_context is now synchronous
                z = self.get_reward_context(self.active_rewards)
                
                # Set the current_z with the tensor (get_reward_context guarantees a tensor)
                self.current_z = z
                
                response = {
                    "type": "reward_updated",
                    "status": "success",
                    "active_rewards": self.active_rewards,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(response))
                logger.info("Update successful")
                
        except Exception as e:
            error_msg = f"Error updating reward: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            
            response = {
                "type": "reward_updated",
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))

    async def handle_mix_pose_reward(self, websocket, data: Dict[str, Any]) -> None:
        """Mix pose-based and reward-based behaviors with enhanced fusion strategies."""
        try:
            logger.info("Mixing pose and reward behaviors...")
            goal_qpos = np.array(data.get("pose", []))
            reward_config = data.get("reward", {})
            mix_weight = data.get("mix_weight", 0.5)
            mix_strategy = data.get("mix_strategy", "mlp_fusion")

            if len(goal_qpos) != 76:
                raise ValueError(f"Invalid pose length: {len(goal_qpos)}, expected 76")

            current_qpos = self.env.unwrapped.data.qpos.copy()
            current_qvel = self.env.unwrapped.data.qvel.copy()

            self.env.unwrapped.set_physics(qpos=goal_qpos, qvel=np.zeros(75))
            goal_obs = torch.tensor(
                self.env.unwrapped.get_obs()["proprio"].reshape(1, -1),
                device=self.model.cfg.device,
                dtype=torch.float32
            )
            self.env.unwrapped.set_physics(qpos=current_qpos, qvel=current_qvel)

            try:
                pose_result = self.model.tracking_inference(next_obs=goal_obs)
                pose_z = await pose_result if asyncio.iscoroutine(pose_result) else pose_result
                reward_z = self.get_reward_context(reward_config)

                pose_z = pose_z.to(self.model.cfg.device)
                reward_z = reward_z.to(self.model.cfg.device)

                if mix_strategy == "linear":
                    result_z = (1 - mix_weight) * pose_z + mix_weight * reward_z
                    logger.info("Using linear interpolation strategy")

                elif mix_strategy == "normalized":
                    combined = (1 - mix_weight) * pose_z + mix_weight * reward_z
                    result_z = torch.nn.functional.normalize(combined, p=2, dim=1)
                    logger.info("Using normalized average strategy")

                elif mix_strategy == "slerp":
                    pose_z_norm = torch.nn.functional.normalize(pose_z, p=2, dim=1)
                    reward_z_norm = torch.nn.functional.normalize(reward_z, p=2, dim=1)
                    dot = torch.sum(pose_z_norm * reward_z_norm, dim=1, keepdim=True).clamp(-1.0, 1.0)
                    omega = torch.acos(dot)
                    sin_omega = torch.sin(omega)
                    result_z = torch.where(
                        sin_omega > 1e-4,
                        (torch.sin((1 - mix_weight) * omega) / sin_omega) * pose_z +
                        (torch.sin(mix_weight * omega) / sin_omega) * reward_z,
                        (1 - mix_weight) * pose_z + mix_weight * reward_z
                    )
                    logger.info("Using spherical interpolation strategy")

                elif mix_strategy == "max_component":
                    mask = (torch.abs(pose_z) > torch.abs(reward_z)).float()
                    result_z = mask * pose_z + (1 - mask) * reward_z
                    logger.info("Using max component strategy")

                elif mix_strategy == "add":
                    result_z = pose_z + reward_z
                    logger.info("Using addition strategy")

                elif mix_strategy == "mlp_fusion":
                    fusion_mlp = torch.nn.Sequential(
                        torch.nn.Linear(2 * pose_z.shape[1], 2 * pose_z.shape[1]),
                        torch.nn.ReLU(),
                        torch.nn.Linear(2 * pose_z.shape[1], pose_z.shape[1])
                    ).to(self.model.cfg.device)
                    with torch.no_grad():
                        result_z = fusion_mlp(torch.cat([pose_z, reward_z], dim=-1))
                    logger.info("Using MLP fusion strategy")

                elif mix_strategy == "gated":
                    gate_layer = torch.nn.Sequential(
                        torch.nn.Linear(2 * pose_z.shape[1], 1),
                        torch.nn.Sigmoid()
                    ).to(self.model.cfg.device)
                    with torch.no_grad():
                        gate = gate_layer(torch.cat([pose_z, reward_z], dim=-1))
                        result_z = gate * pose_z + (1 - gate) * reward_z
                    logger.info("Using adaptive gating strategy")

                else:
                    result_z = (1 - mix_weight) * pose_z + mix_weight * reward_z
                    logger.warning(f"Unknown mix strategy '{mix_strategy}', defaulting to linear")

            except Exception as e:
                result_z = (1 - mix_weight) * pose_z + mix_weight * reward_z
                logger.error(f"Error in {mix_strategy} strategy: {str(e)}, falling back to linear")

            self.current_z = result_z

            response = {
                "type": "mix_updated",
                "status": "success",
                "mix_weight": mix_weight,
                "mix_strategy": mix_strategy,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))

        except Exception as e:
            error_msg = f"Error mixing behaviors: {str(e)}"
            logger.error(error_msg)
            response = {
                "type": "mix_updated",
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))


    async def handle_debug_model_info(self, websocket, data: Dict[str, Any]) -> None:
        """Send debug information about model state"""
        stats = self.ws_manager.get_stats()
        response = {
            "type": "debug_model_info",
            "is_computing": self.is_computing_reward,
            "active_rewards": self.active_rewards,
            "active_poses": self.active_poses,
            **stats
        }
        
        # Include computation status if available and client requested it
        if hasattr(self, 'computation_status') and self.computation_status:
            # Include the status but don't repeat it in future requests
            computation_status = self.computation_status
            self.computation_status = None  # Clear after sending once
            response['computation_status'] = computation_status
        
        # Only send to the requesting client instead of broadcasting to all
        await websocket.send(json.dumps(response))
        logger.debug("Sent debug model info to requesting client")

    async def handle_request_reward(self, websocket, data: Dict[str, Any]) -> None:
        """Process reward combination requests"""
        logger.info("------------------------------------------------------------------------")
        logger.info("Processing reward combination request")
        
        # Store the originating websocket for sending computation status later
        self.last_websocket = websocket
        
        # Extract message_id from request or generate a new one
        message_id = data.get("message_id", f"reward_req_{int(time.time() * 1000)}")
        
        # Check for ongoing computation - regardless of batch or single
        if self.is_computing_reward:
            logger.warning("Reward computation already in progress, request queued")
            # Return a "queued" status so client knows we received it
            response = {
                "type": "reward",
                "status": "computing_in_progress",
                "message": "Request received - will process when current computation completes",
                "message_id": f"{message_id}_queued",
                "timestamp": data.get("timestamp", ""),
                "is_computing": True
            }
            await websocket.send(json.dumps(response))
            return

        try:
            # Check if reward config is empty
            if not data.get('reward', {}).get('rewards'):
                logger.info("No rewards in configuration - treating as clean rewards")
                await self.handle_clean_rewards(websocket, data)
                return
                
            # Process rewards in batch mode
            # Check if this contains multiple rewards or is adding to existing
            is_adding_reward = data.get('add_to_existing', False)
            is_batch_mode = data.get('batch_mode', False) or len(data.get('reward', {}).get('rewards', [])) > 1
            
            if is_adding_reward and self.active_rewards is not None:
                # Add the new reward to existing rewards
                logger.info("Adding new reward to existing rewards")
                
                # Get the existing rewards and weights
                existing_rewards = self.active_rewards.get('rewards', [])
                existing_weights = self.active_rewards.get('weights', [])
                
                # Get the new rewards and weights
                new_rewards = data['reward'].get('rewards', [])
                new_weights = data['reward'].get('weights', [])
                
                # Combine them
                combined_rewards = existing_rewards + new_rewards
                combined_weights = existing_weights + new_weights
                
                # Create the updated reward config
                self.active_rewards = {
                    'rewards': combined_rewards,
                    'weights': combined_weights,
                    'combinationType': data['reward'].get('combinationType', 
                                                        self.active_rewards.get('combinationType', 'geometric'))
                }
                
                logger.info(f"Combined {len(existing_rewards)} existing rewards with {len(new_rewards)} new rewards")
            else:
                # Replace existing rewards with the new configuration
                logger.info("Setting new reward configuration")
                self.active_rewards = data['reward']
            
            # Update current reward configuration
            self.current_reward_config = self.active_rewards
            
            # For all cases (batch or single), use the simple async approach
            logger.info(f"Computing context for {len(self.active_rewards.get('rewards', []))} rewards")
            
            # Create a standard cache key
            standard_key = self.context_cache.get_cache_key(self.active_rewards)
            
            # Start the computation and get the immediate result (current context)
            # This returns immediately but updates self.current_z when done in background
            z = self.get_reward_context(self.active_rewards)
            
            # Note: we don't need to set self.current_z - it will be updated by
            # the background task when computation is complete
            
            response = {
                "type": "reward",
                "value": 1.0,
                "message_id": f"{message_id}_processed",
                "timestamp": data.get("timestamp", ""),
                "is_computing": self.is_computing_reward,
                "active_rewards": self.active_rewards,
                "batch_mode": is_batch_mode
            }
            await websocket.send(json.dumps(response))
            
            logger.info(f"Active Rewards: {len(self.active_rewards['rewards'])}")
            logger.info(f"Cached Computations: {len(self.context_cache.computation_cache)}")
            logger.info("------------------------------------------------------------------------")

        except Exception as e:
            logger.error(f"Error processing reward request: {str(e)}")
            response = {
                "type": "reward",
                "status": "error",
                "error": str(e),
                "message_id": f"{message_id}_error",
                "timestamp": data.get("timestamp", ""),
                "is_computing": False
            }
            await websocket.send(json.dumps(response))
            
            
    async def handle_clean_rewards(self, websocket, data: Dict[str, Any]) -> None:
        """Reset all rewards and environment state"""
        logger.info("Cleaning active rewards...")
        
        self.current_z = self.default_z
        self.active_rewards = None
        
        observation, _ = self.env.reset()
        logger.info("Environment reset completed")
        
        # Send debug info only to the requesting client
        debug_info = {
            "type": "debug_model_info",
            "is_computing": self.is_computing_reward,
            "active_rewards": self.active_rewards,
            "message_id": f"clean_debug_{int(time.time() * 1000)}",
            **self.ws_manager.get_stats()
        }
        await websocket.send(json.dumps(debug_info))
        
        response = {
            "type": "clean_rewards",
            "status": "success",
            "message_id": f"clean_success_{int(time.time() * 1000)}",
            "timestamp": data.get("timestamp", "")
        }
        await websocket.send(json.dumps(response))

    async def handle_update_parameters(self, websocket, data: Dict[str, Any]) -> None:
        """Update environment parameters"""
        new_params = data.get("parameters", {})
        logger.info("Updating environment parameters")
        self.env.update_parameters(new_params)
        
        response = {
            "type": "parameters_updated",
            "parameters": self.env.get_parameters(),
            "timestamp": data.get("timestamp", "")
        }
        await websocket.send(json.dumps(response))

    async def handle_load_pose_smpl(self, websocket, data: Dict[str, Any]) -> None:
        """Load pose from SMPL format data"""
        try:
            logger.info("Processing SMPL pose as goal...")
            smpl_pose = np.array(data.get("pose", []))
            smpl_trans = np.array(data.get("trans", [0, 0, 0.91437225]))
            model_type = data.get("model", "smpl")
            
            if len(smpl_pose) != 72:
                raise ValueError(f"Invalid SMPL pose length: {len(smpl_pose)}, expected 72")
            
            smpl_pose = torch.tensor(smpl_pose).reshape(1, 72)
            smpl_trans = np.array(smpl_trans).reshape(1, 3)
            
            # Convert SMPL pose to qpos
            from utils.smpl_utils import smpl_to_qpose
            goal_qpos = smpl_to_qpose(
                pose=smpl_pose,
                mj_model=self.env.unwrapped.model,
                trans=smpl_trans,
                smpl_model=model_type
            )
            
            # Store current state
            current_qpos = self.env.unwrapped.data.qpos.copy()
            current_qvel = self.env.unwrapped.data.qvel.copy()
            
            # Set goal state temporarily
            self.env.unwrapped.set_physics(
                qpos=goal_qpos.flatten(),
                qvel=np.zeros(75)
            )
            
            goal_obs = torch.tensor(
                self.env.unwrapped.get_obs()["proprio"].reshape(1, -1),
                device=self.model.cfg.device,
                dtype=torch.float32
            )
            
            # Restore original state
            self.env.unwrapped.set_physics(
                qpos=current_qpos,
                qvel=current_qvel
            )
            
            # Get context using specified inference type
            inference_type = data.get("inference_type", "goal")
            
            # Execute inference based on type
            try:
                # Get inference result and await if needed
                if inference_type == "goal":
                    result = self.model.goal_inference(next_obs=goal_obs)
                elif inference_type == "tracking":
                    result = self.model.tracking_inference(next_obs=goal_obs)
                else:
                    raise ValueError(f"Unsupported inference type: {inference_type}")
              
                z = result
                
                # Update current context 
                self.current_z = z
                
            except Exception as e:
                logger.error(f"Error in SMPL inference: {str(e)}")
                # Use default z if available
                if hasattr(self, 'default_z'):
                    self.current_z = self.default_z
                else:
                    raise
            
            # Update active poses
            self.active_poses = {
                "type": "smpl",
                "pose": smpl_pose.tolist(),
                "trans": smpl_trans.tolist(),
                "model": model_type,
                "inference_type": inference_type,
                "qpos": goal_qpos.tolist()
            }
            
            logger.info("Context updated successfully")
            
            response = {
                "type": "pose_loaded",
                "status": "success",
                "inference_type": inference_type,
                "active_poses": self.active_poses,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))
            
        except Exception as e:
            error_msg = f"Error processing SMPL pose: {str(e)}"
            logger.error(error_msg)
            
            response = {
                "type": "pose_loaded",
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))

    async def handle_get_current_context(self, websocket, data: Dict[str, Any]) -> None:
        """Handle request for current context information"""
        try:
            logger.info("Getting current context information...")
            
            # Get cache file path if we have a current reward config
            cache_file = None
            if self.current_reward_config is not None:
                cache_key = self.context_cache.get_cache_key(self.current_reward_config)
                cache_file = self.context_cache._get_cache_file(cache_key)
            
            # Get environment parameters
            env_params = self.env.get_parameters() if hasattr(self.env, 'get_parameters') else {}
            
            response = {
                "type": "current_context",
                "status": "success",
                "data": {
                    "active_rewards": self.active_rewards,
                    "active_poses": self.active_poses,
                    "current_reward_config": self.current_reward_config,
                    "cache_file": str(cache_file) if cache_file else None,
                    "is_computing": self.is_computing_reward,
                    "environment_variables": {
                        "backend_domain": self.backend_domain,
                        "webserver_port": self.webserver_port,
                        "ws_port": self.ws_port,
                        "api_port": self.api_port
                    },
                    "environment_parameters": env_params
                },
                "timestamp": datetime.now().isoformat()
            }
            
            await websocket.send(json.dumps(response))
            logger.info("Current context information sent")
            
        except Exception as e:
            error_msg = f"Error getting current context: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            
            response = {
                "type": "current_context",
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))

    async def handle_load_npz_context(self, websocket, data: Dict[str, Any]) -> None:
        """Handle loading context directly from an NPZ file"""
        try:
            logger.info("Loading context from NPZ file...")
            npz_path = data.get("npz_path")
            
            if not npz_path:
                raise ValueError("NPZ path not provided")
            
            # Load the context from NPZ
            try:
                npz_data = np.load(npz_path)
                z = torch.from_numpy(npz_data['z']).to(device=self.model.cfg.device, dtype=torch.float32)
                logger.info(f"Loaded context tensor of shape {z.shape} from {npz_path}")
                
                # Update current context
                self.current_z = z
                
                # Try to infer reward config from filename
                cache_dir = Path(os.path.expanduser('~/.motivo/cache'))
                if Path(npz_path).parent == cache_dir:
                    # This is a cached reward config, try to find the original config
                    hash_value = Path(npz_path).stem
                    logger.info(f"NPZ file is from cache, hash: {hash_value}")
                else:
                    logger.info("NPZ file is not from cache directory")
                
                response = {
                    "type": "npz_context_loaded",
                    "status": "success",
                    "timestamp": datetime.now().isoformat(),
                    "npz_path": npz_path,
                    "tensor_shape": list(z.shape)
                }
                
            except Exception as e:
                raise ValueError(f"Failed to load NPZ file: {str(e)}")
            
            await websocket.send(json.dumps(response))
            logger.info("Context loaded successfully")
            
        except Exception as e:
            error_msg = f"Error loading NPZ context: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            
            response = {
                "type": "npz_context_loaded",
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))

    def get_current_z(self):
        """Get the current context tensor - never returns a coroutine"""
        # If current_z is None, use default_z if available
        if self.current_z is None and hasattr(self, 'default_z'):
            return self.default_z
            
      
            
        # Return the tensor
        return self.current_z

    async def handle_capture_frame(self, websocket, data: Dict[str, Any]) -> None:
        """Handle request to capture and save the current frame"""
        try:
            logger.info("Received request to capture frame")
            
            # Get the current frame from the environment
            frame = self.env.render()
            
            # Get display manager overlay if available
            frame_with_overlays = frame
            if hasattr(self.env, 'display_manager') and self.env.display_manager:
                frame_with_overlays = self.env.display_manager.show_frame(
                    frame,
                    q_percentage=0.0,  # We don't have this value here
                    is_computing=self.is_computing_reward
                )
                
            # Save the frame
            resize_width = data.get("resize_width", 640)
            frame_path = save_shared_frame(frame_with_overlays, resize_width=resize_width)
            
            
            
            # Log the path information
            logger.info(f"Frame captured and saved at absolute path: '{frame_path}'")
            
            # Respond with success
            response = {
                "type": "frame_captured",
                "status": "success",
                "frame_path": frame_path,
                "timestamp": datetime.now().isoformat()
            }
            
            # Include requestId if it was provided
            if "requestId" in data:
                response["requestId"] = data["requestId"]
                
            await websocket.send(json.dumps(response))
            logger.info("Frame successfully captured and saved")
            
        except Exception as e:
            logger.error(f"Error capturing frame: {str(e)}")
            traceback.print_exc()
            
            # Send error response
            response = {
                "type": "frame_captured",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            
            # Include requestId if it was provided
            if "requestId" in data:
                response["requestId"] = data["requestId"]
                
            await websocket.send(json.dumps(response))
            
    async def handle_make_snapshot(self, websocket, data: Dict[str, Any]) -> None:
        """Handle request to make a snapshot of the current frame with timestamp for Gemini"""
        try:
            logger.info("Received request to make snapshot for Gemini")
            
            # Get the current frame from the environment
            frame = self.env.render()
            
            # Get display manager overlay if available
            frame_with_overlays = frame
            if hasattr(self.env, 'display_manager') and self.env.display_manager:
                frame_with_overlays = self.env.display_manager.show_frame(
                    frame,
                    q_percentage=0.0,
                    is_computing=self.is_computing_reward
                )
                
            # Create a timestamp-based filename for this capture
            timestamp = int(datetime.now().timestamp())
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_filename = f"gemini_snapshot_{timestamp}.jpg"
            
            # Save the frame to both shared_frames and public dir
            from core.config import config
            
            resize_width = data.get("resize_width", 640)
            
            # First save to shared_frames directory (used by Motivo server)
            frame_path = save_shared_frame(frame_with_overlays, resize_width=resize_width)
            
            # Also save a timestamped copy
            try:
                # Resize image while preserving aspect ratio
                h, w = frame_with_overlays.shape[:2]
                aspect_ratio = h / w
                new_width = resize_width
                new_height = int(new_width * aspect_ratio)
                
                # Resize the image
                resized_frame = cv2.resize(frame_with_overlays, (new_width, new_height), interpolation=cv2.INTER_AREA)
                
                # Convert RGB to BGR for OpenCV
                bgr_frame = cv2.cvtColor(resized_frame, cv2.COLOR_RGB2BGR)
                
                # Save timestamped image to shared_frames_dir
                timestamped_path = os.path.join(config.shared_frames_dir, snapshot_filename)
                cv2.imwrite(timestamped_path, bgr_frame)
                logger.info(f"Saved timestamped snapshot: {timestamped_path}")
                
                # Save a copy to public directory for web access
                public_frames_dir = os.path.join(os.path.dirname(config.public_dir), 'public', 'storage', 'shared_frames')
                os.makedirs(public_frames_dir, exist_ok=True)
                public_timestamped_path = os.path.join(public_frames_dir, snapshot_filename)
                cv2.imwrite(public_timestamped_path, bgr_frame)
                logger.info(f"Saved public copy of snapshot: {public_timestamped_path}")
                
                # Create the public URL path for browser access
                image_url_path = f"/storage/shared_frames/{snapshot_filename}"
                
            except Exception as e:
                logger.error(f"Error saving timestamped snapshot: {str(e)}")
                timestamped_path = None
                image_url_path = None
            
            # Respond with success
            response = {
                "type": "snapshot_created",
                "status": "success",
                "frame_path": frame_path,
                "timestamped_path": timestamped_path,
                "public_path": image_url_path,
                "timestamp": timestamp,
                "timestamp_str": timestamp_str
            }
            await websocket.send(json.dumps(response))
            logger.info("Snapshot successfully created and saved")
            
        except Exception as e:
            logger.error(f"Error creating snapshot: {str(e)}")
            traceback.print_exc()
            
            # Send error response
            response = {
                "type": "snapshot_created",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(response))
    
    def set_default_z(self, z: torch.Tensor) -> None:
        """Set the default context tensor"""
        self.default_z = z
        self.current_z = z
        logger.info("Default context set")

    async def handle_get_target_positions(self, websocket, data: Dict[str, Any]) -> None:
        """Handle request to get current positions of all reward targets and body parts"""
        try:
            logger.info("Getting current target positions and all body part positions...")
            
            # Import here to avoid circular imports
            from rewards.position_rewards import PositionReward, transform_point_to_local_frame, get_rotation_matrix_from_pelvis
            
            positions_data = {}
            all_body_positions = {}
            
            # Get reference frame data for local coordinate calculations
            pelvis_pos = self.env.unwrapped.data.xpos[self.env.unwrapped.model.body("Pelvis").id].copy()
            pelvis_rotation = get_rotation_matrix_from_pelvis(
                self.env.unwrapped.model, 
                self.env.unwrapped.data
            )
            
            # Get positions for all body parts
            standard_body_parts = [
                "Head", "Pelvis", "L_Hand", "R_Hand", "L_Toe", "R_Toe", "Torso", "Chest"
            ]
            
            # First collect all bodies in the model
            all_bodies = {}
            for i in range(self.env.unwrapped.model.nbody):
                body_name = self.env.unwrapped.model.body(i).name
                all_bodies[body_name] = i
            
            # Get positions for all bodies
            for body_name, body_id in all_bodies.items():
                current_pos = self.env.unwrapped.data.xpos[body_id].copy()
                
                
                position_data = {
                    "global": {
                        "x": float(current_pos[0]),
                        "y": float(current_pos[1]),
                        "z": float(current_pos[2])
                    }
                }
              

                #position_data = {}
                
                # Calculate local position relative to pelvis
                '''
                local_pos = transform_point_to_local_frame(current_pos, pelvis_pos, pelvis_rotation)
                position_data["local"] = {
                    "x": float(local_pos[0]),
                    "y": float(local_pos[1]),
                    "z": float(local_pos[2])
                }
                '''
                
                all_body_positions[body_name] = position_data
            
            # Also process position rewards if any are active
            if self.active_rewards and 'rewards' in self.active_rewards:
                for reward_config in self.active_rewards['rewards']:
                    reward_name = reward_config.get('name', '')
                    
                    # Check if this is a position reward
                    if reward_name.startswith('position-'):
                        try:
                            reward_obj = PositionReward.reward_from_name(reward_name)
                            
                            if reward_obj:
                                # Get target configurations
                                targets = reward_obj.get_serialized_targets()
                                
                                # Get current positions
                                current_positions = reward_obj.get_current_positions(
                                    self.env.unwrapped.model,
                                    self.env.unwrapped.data
                                )
                                
                                positions_data[reward_name] = {
                                    "targets": targets,
                                    "current_positions": current_positions
                                }
                        except Exception as e:
                            logger.warning(f"Error processing position reward {reward_name}: {str(e)}")
                            continue
            
            response = {
                "type": "target_positions",
                "status": "success",
                "data": {
                    "reward_positions": positions_data,
                    "all_body_positions": all_body_positions
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Include requestId if provided in the original request
            if "requestId" in data:
                response["requestId"] = data["requestId"]
                
            await websocket.send(json.dumps(response))
            logger.info(f"Sent position data for {len(all_body_positions)} body parts and {len(positions_data)} rewards")
            
        except Exception as e:
            error_msg = f"Error getting target positions: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            
            response = {
                "type": "target_positions",
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            
            # Include requestId if provided in the original request
            if "requestId" in data:
                response["requestId"] = data["requestId"]
                
            await websocket.send(json.dumps(response))

# Register cleanup function after the class is defined
def _cleanup_message_handlers_at_exit():
    if hasattr(MessageHandler, 'cleanup_all'):
        logger.info("Running MessageHandler cleanup at exit")
        MessageHandler.cleanup_all()
    
# Register the cleanup function
atexit.register(_cleanup_message_handlers_at_exit)