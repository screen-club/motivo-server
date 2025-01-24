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

# import from env BACKEND_DOMAIN
BACKEND_DOMAIN = os.getenv("VITE_BACKEND_DOMAIN", "localhost")
WS_PORT = os.getenv("VITE_WS_PORT", 8765)
API_PORT = os.getenv("VITE_API_PORT", 5000)

# Global variables
model = None
env = None
buffer_data = None
active_contexts = {}  # Store computed contexts
current_z = None     # Current active context
thread_pool = ThreadPoolExecutor(max_workers=1)  # Increased from 1 to 2
is_computing_reward = False  # New flag to track reward computation status

async def get_reward_context(reward_config):
    """Async wrapper for reward context computation"""
    global is_computing_reward
    
    try:
        is_computing_reward = True
        print("\n=== Reward Context Computation ===")
        print("Computing... ⚙️")
        print(f"Input config: {json.dumps(reward_config, indent=2)}")
        
        loop = asyncio.get_event_loop()
        z = await loop.run_in_executor(
            thread_pool, 
            compute_reward_context, 
            reward_config, 
            env, 
            model, 
            buffer_data
        )
        return z
    finally:
        is_computing_reward = False
        print("✅ Computation complete!")

async def handle_websocket(websocket):
    """Handle websocket connections"""
    global current_z, active_contexts, is_computing_reward
    
    print("\n=== New WebSocket Connection Established ===")
    
    # Update to use env.unwrapped to access model and data
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                message_type = data.get("type", "")

                if message_type == "debug_model_info":
                    response = {
                        "type": "debug_model_info",
                        "is_computing": is_computing_reward
                    }
                    await websocket.send(json.dumps(response))
                
                elif message_type == "request_reward":
                    config_key = json.dumps(data['reward'], sort_keys=True)
                    print(f"\nProcessing reward request...")
                    print(f"Active contexts before: {len(active_contexts)}")
                    
                    # Check if we already computed this reward context
                    if config_key in active_contexts:
                        print("Using cached reward context")
                        current_z = active_contexts[config_key]
                    else:
                        print("Computing new reward context...")
                        # Move combination_type into the reward config
                        reward_config = data['reward']
                        if 'combination_type' in data:
                            reward_config['combination_type'] = data['combination_type']
                        
                        # Compute and cache new context
                        z = await get_reward_context(reward_config)
                        active_contexts[config_key] = z
                        current_z = z
                    
                    response = {
                        "type": "reward",
                        "value": 1.0,
                        "timestamp": data.get("timestamp", ""),
                        "is_computing": is_computing_reward
                    }
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
                    
                elif message_type == "update_parameters":
                    # Handle parameter updates - call update_parameters directly on env
                    new_params = data.get("parameters", {})
                    env.update_parameters(new_params)  # Changed from env.unwrapped.update_parameters
                    
                    # Send confirmation back to client
                    response = {
                        "type": "parameters_updated",
                        "parameters": env.get_parameters(),  # Changed from env.unwrapped.get_parameters
                        "timestamp": data.get("timestamp", "")
                    }
                    await websocket.send(json.dumps(response))

                elif message_type == "get_parameters":
                    # Return current parameter values
                    response = {
                        "type": "parameters",
                        "parameters": env.get_parameters(),  # Changed from env.unwrapped.get_parameters
                        "timestamp": data.get("timestamp", "")
                    }
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
    global current_z, is_computing_reward
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
        
        # Add computing indicator text
        if is_computing_reward:
            cv2.putText(
                frame,
                "Computing rewards...",
                (10, 60),  # Position just below Q-value
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,  # Smaller font size
                (255, 255, 0),  # Yellow color
                1  # Thinner line
            )
        
        # Resize frame to 320x240 before saving
        resized_frame = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)
        
        cv2.imshow("Humanoid Simulation", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        cv2.imwrite('../output.jpg', resized_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break
        elif key == ord('s'):  # Press 's' to save frame
            try:
                # Get the raw observation tensor
                
                # Get data from environment
                env_data = env.unwrapped.data
                
                # Print available data fields for debugging
                
                
              
                print("GO")
                # Save frame with state data
                save_frame_data(
                    frame=frame,
                    qpos=env_data.qpos.copy(),
                    qvel=env_data.qvel.copy(),
                    env=env  # Pass the environment instance
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
        # Device selection with CUDA support
        if torch.cuda.is_available():
            device = "cuda"
            torch.backends.cudnn.benchmark = True  # Enable CUDA optimization
        elif torch.backends.mps.is_available():
            device = "mps"  # Apple Silicon GPU
        else:
            device = "cpu"
        print(f"Using device: {device}")
        
        print("Loading model and environment...")
        model = FBcprModel.from_pretrained("facebook/metamotivo-M-1")
        model.to(device)
        model.eval()
        
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
        server = await websockets.serve(handle_websocket, "0.0.0.0", WS_PORT)
        print(f"WebSocket server started at ws://{BACKEND_DOMAIN}:{WS_PORT}")
        
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
