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

from env_setup import setup_environment
from buffer_utils import download_buffer
from reward_context import compute_reward_context, compute_q_value
from custom_rewards import print_model_info, list_model_body_names
from humenv import rewards as humenv_rewards
from typing import Dict, Any

# Global variables
model = None
env = None
buffer_data = None
active_contexts = {}  # Store computed contexts
current_z = None     # Current active context
thread_pool = ThreadPoolExecutor(max_workers=1)  # Increased from 1 to 2

async def get_reward_context(reward_config):
    """Async wrapper for reward context computation"""
    print("\n=== Reward Context Computation ===")
    print("Computing... ⚙️")  # Added loading indicator
    print(f"Input config: {json.dumps(reward_config, indent=2)}")
    
    # Show loading animation in the window
    loading_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(loading_frame, "Computing Reward Context...", (180, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(loading_frame, "Please wait ⚙️", (250, 250),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.imshow("Humanoid Simulation", loading_frame)
    cv2.waitKey(1)
    
    loop = asyncio.get_event_loop()
    z = await loop.run_in_executor(
        thread_pool, 
        compute_reward_context, 
        reward_config, 
        env, 
        model, 
        buffer_data
    )
    print("✅ Computation complete!")
    print(f"Computed context shape: {z.shape}")
    print(f"Context values (first 5): {z[:5].tolist()}")
    return z

async def handle_websocket(websocket):
    """Handle websocket connections"""
    global current_z, active_contexts
    
    print("\n=== New WebSocket Connection Established ===")
    
    # Update to use env.unwrapped to access model and data
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                message_type = data.get("type", "")

                if message_type == "debug_model_info":
                    print("hello")
                    await websocket.send("hello")
                
                elif message_type == "request_reward":
                    config_key = json.dumps(data['reward'], sort_keys=True)
                    print(f"\nProcessing reward request...")
                    print(f"Active contexts before: {len(active_contexts)}")
                    
                    # Clear previous contexts without resetting environment
                    active_contexts.clear()
                    print(f"Cleared contexts. Active contexts after: {len(active_contexts)}")
                    
                    # Move combination_type into the reward config
                    reward_config = data['reward']
                    if 'combination_type' in data:
                        reward_config['combination_type'] = data['combination_type']
                    
                    # Compute and set new context
                    print("\nComputing new reward context...")
                    z = await get_reward_context(reward_config)
                    active_contexts[config_key] = z
                    current_z = z
                    print(f"New context stored with key: {config_key[:100]}...")
                    
                    response = {
                        "type": "reward",
                        "value": 1.0,
                        "timestamp": data.get("timestamp", "")
                    }
                    print(f"Sending response: {response}")
                    await websocket.send(json.dumps(response))
                    
                elif message_type == "clean_rewards":
                    print("\nCleaning rewards...")
                    print(f"Active contexts before cleaning: {len(active_contexts)}")
                    active_contexts.clear()
                    
                    # Set default standing behavior
                    default_config = {
                        'rewards': [
                            { 'name': 'move-ego', 'move_speed': 0.0, 'stand_height': 1.4 }
                        ],
                        'weights': [1.0]
                    }
                    print("\nSetting default standing behavior:")
                    print(f"Default config: {json.dumps(default_config, indent=2)}")
                    
                    z = await get_reward_context(default_config)
                    current_z = z
                    
                    # Reset environment
                    observation, _ = env.reset()
                    print("Environment reset completed")
                    
                    response = {
                        "type": "clean_rewards",
                        "status": "success",
                        "timestamp": data.get("timestamp", "")
                    }
                    print(f"Sending response: {response}")
                    await websocket.send(json.dumps(response))
                    
            except json.JSONDecodeError:
                print("Error: Invalid JSON message")
                await websocket.send(json.dumps({"error": "Invalid JSON"}))
                
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        if env:
            env.close()

async def run_simulation():
    """Continuous simulation loop"""
    global current_z
    observation, _ = env.reset()
    
    frame_counter = 0
    q_value = 0.0
    
    # Initialize with default context if none exists
    if current_z is None:
        print("\nInitializing with default 'stand' behavior...")
        default_config = {
            'rewards': [
                { 'name': 'move-ego', 'move_speed': 0.0, 'stand_height': 1.4 }
            ],
            'weights': [1.0]
        }
        current_z = await get_reward_context(default_config)
    
    while True:
        # Get action first
        action = model.act(observation, current_z, mean=True)
        q_value = compute_q_value(model, observation, current_z, action)
        
        # Step the environment
        observation, _, terminated, truncated, _ = env.step(
            action.cpu().numpy().ravel()
        )
        
        # Render frame with Q-value overlay
        frame = env.render()
        cv2.putText(
            frame,
            f"Q-value: {q_value:.3f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2
        )
        
        cv2.imshow("Humanoid Simulation", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break
        elif key == ord('s'):  # Press 's' to save frame
            try:
                # Get the raw observation tensor
                obs_tensor = observation.detach().cpu().numpy()
                
                # Get data from environment
                env_data = env.unwrapped.data
                
                # Print available data fields for debugging
                print("\nAvailable data fields:")
                print(dir(env_data))
                
                # Extract SMPL parameters from environment data
                smpl_data = {
                    'poses': env_data.qpos.copy(),  # Joint positions
                    'betas': env_data.body_xpos.copy(),  # Body parameters
                    'trans': env_data.body_xpos[0].copy()  # Root translation (first body)
                }
                
                # Save frame with state data
                save_frame_data(
                    frame=frame,
                    qpos=env_data.qpos.copy(),
                    qvel=env_data.qvel.copy(),
                    smpl_data=smpl_data
                )
                print("Frame saved! 📸")
                
            except Exception as e:
                print("Error during frame save:", str(e))
                print("Observation shape:", observation.shape)
                print("Data structure:", type(env.unwrapped.data))
        
        if terminated:
            observation, _ = env.reset()
        
        await asyncio.sleep(1/60)

async def main():
    """Main function"""
    global model, env, buffer_data
    
    try:
        # Modified device selection for M1 Macs
        if torch.backends.mps.is_available():
            device = "mps"  # Apple Silicon GPU
        else:
            device = "cpu"
        print(f"Using device: {device}")
        
        print("Loading model and environment...")
        model = FBcprModel.from_pretrained("facebook/metamotivo-M-1")
        model.to(device)
        model.eval()
        
        # Remove CUDA-specific optimization
        # if device == "cuda":
        #     torch.backends.cudnn.benchmark = True
        
        env = setup_environment(device)
        
        print("Downloading buffer data...")
        buffer_data = download_buffer()
        
        # Pre-compute default context to avoid initial lag
        default_config = {
            'rewards': [
                { 'name': 'move-ego', 'move_speed': 0.0, 'stand_height': 1.4 }
            ],
            'weights': [1.0]
        }
        print("\nPre-computing default context...")
        current_z = await get_reward_context(default_config)
        
        print("\nStarting WebSocket server and simulation...")
        server = await websockets.serve(handle_websocket, "localhost", 8765)
        print("WebSocket server running on ws://localhost:8765")
        
        await asyncio.gather(
            server.wait_closed(),
            run_simulation()
        )
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        thread_pool.shutdown()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    asyncio.run(main())
