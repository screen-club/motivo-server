import asyncio
import websockets
import logging
import json
import numpy as np
import os
import time
from datetime import datetime
from scipy.spatial.transform import Rotation as R
from pathlib import Path
from lib.api import APIClient
import requests
import argparse

# Configuration
CONFIG = {
    'WS_URI': 'ws://51.159.163.145:8765',
    'WS_URI_LOCAL': 'ws://localhost:8765',
    'API_URL': 'http://51.159.163.145:5002',
    'API_URL_LOCAL': 'http://localhost:5002',
    'MAX_RETRIES': 3,
    'RETRY_DELAY': 2,
    'DEFAULT_FPS': 4,  # Default frames per second for websocket streaming
    'TARGET_FPS': 30,  # FPS for database storage
    'FRAME_DELAY': 0.25,  # 1/DEFAULT_FPS
    'RESPONSE_TIMEOUT': 30,
    'HEARTBEAT_INTERVAL': 10
}

# Configure logging
logging.basicConfig(level=logging.INFO)  # Changed from DEBUG to INFO
logger = logging.getLogger(__name__)
# Reduce websockets protocol logging even further
logging.getLogger('websockets').setLevel(logging.WARNING)
# Prevent asyncio debug logs
logging.getLogger('asyncio').setLevel(logging.WARNING)

# SMPL joint definitions
SKEL_JOINTS = [
    "Pelvis", "L_Hip", "R_Hip", "Torso", "L_Knee", "R_Knee", "Spine",
    "L_Ankle", "R_Ankle", "Chest", "L_Toe", "R_Toe", "Neck", "L_Thorax",
    "R_Thorax", "Head", "L_Shoulder", "R_Shoulder", "L_Elbow", "R_Elbow",
    "L_Wrist", "R_Wrist", "L_Hand", "R_Hand"
]

def get_frame_indices(total_frames, fps):
    """Calculate which frames to keep based on desired FPS"""
    if fps <= 0:
        return []
    
    # Calculate frame interval to achieve desired FPS
    original_fps = CONFIG['TARGET_FPS']
    interval = original_fps / fps
    
    # Generate frame indices
    return [int(i * interval) for i in range(total_frames) if int(i * interval) < total_frames]

def convert_npz_to_smpl(npz_path):
    """Convert NPZ animation data to SMPL format"""
    try:
        # Load NPZ file
        data = np.load(npz_path)
        print(f"Loaded NPZ data: {data.files}")
        poses = data['poses']
        
        # Initialize SMPL arrays
        num_frames = poses.shape[0]
        smpl_poses = np.zeros((num_frames, len(SKEL_JOINTS) * 3))
        
        # Convert poses to SMPL format
        for frame in range(num_frames):
            frame_poses = poses[frame]
            
            # Convert rotation vectors to SMPL format
            for joint_idx in range(len(SKEL_JOINTS)):
                start_idx = joint_idx * 3
                joint_rot = frame_poses[start_idx:start_idx + 3]
                
                # Convert to rotation vector format expected by SMPL
                rot = R.from_rotvec(joint_rot)
                smpl_rot = rot.as_rotvec()
                
                smpl_poses[frame, start_idx:start_idx + 3] = smpl_rot
        
        # Default translation if not in NPZ
        smpl_trans = np.array([[0.0, 0.0, 0.91437225]] * num_frames)
        if 'trans' in data:
            smpl_trans = data['trans']
            
        return {
            'poses': smpl_poses.tolist(),
            'trans': smpl_trans.tolist()
        }
        
    except Exception as e:
        logger.error(f"Error converting NPZ to SMPL: {e}")
        return None

def prepare_animation_for_db(poses, trans):
    """Convert animation data to database format"""
    return {
        "type": "smpl",
        "inference_type": "goal",
        "model": "smpl",
        "pose": poses,
        "trans": trans
    }

async def parse_users_input(users_input):
    """Parse comma-separated users input into a list or None"""
    if not users_input or users_input.strip() == "":
        return None
    
    # Split by comma and strip whitespace from each name
    return [user.strip() for user in users_input.split(",") if user.strip()]

async def upload_npz_to_db(npz_path, users=None):
    """Convert NPZ file and upload to database"""
    try:
        # Convert NPZ to SMPL format
        smpl_data = convert_npz_to_smpl(npz_path)
        if not smpl_data:
            logger.error("Failed to convert NPZ to SMPL format")
            return False
            
        # Get animation name from filename
        animation_name = Path(npz_path).stem
        
        # Prepare data for database
        db_data = prepare_animation_for_db(
            poses=smpl_data['poses'],
            trans=smpl_data['trans']
        )
        
        # Use APIClient to upload to database
        api_client = APIClient(CONFIG['API_URL'])
        result = await asyncio.to_thread(
            api_client.add_config, # Assuming add_config is synchronous
            title=animation_name,
            data=db_data,
            type="pose",
            users=users
        )
        
        if result: # Assuming add_config returns something truthy on success
             logger.info(f"Successfully uploaded animation '{animation_name}' to database")
             return True
        else:
             logger.error(f"Failed to upload animation '{animation_name}' via APIClient")
             return False
        
    except Exception as e:
        logger.error(f"Error uploading animation to database: {e}")
        return False

async def upload_npz_folder_to_db(folder_path, users=None):
    """Upload all NPZ files in folder to database"""
    try:
        npz_files = [f for f in os.listdir(folder_path) if f.endswith('.npz')]
        if not npz_files:
            logger.info(f"No NPZ files found in folder: {folder_path}")
            return
            
        logger.info(f"Found {len(npz_files)} NPZ files to upload")
        
        for npz_file in npz_files:
            full_path = os.path.join(folder_path, npz_file)
            logger.info(f"Processing: {npz_file}")
            
            success = await upload_npz_to_db(full_path, users)
            if success:
                logger.info(f"Successfully uploaded: {npz_file}")
            else:
                logger.error(f"Failed to upload: {npz_file}")
            
    except Exception as e:
        logger.error(f"Error processing folder: {e}")

async def response_handler(websocket, stop_event):
    """Handle WebSocket responses without blocking frame sending"""
    try:
        # Keep track of received updates to detect high load
        receive_buffer = bytearray(1024 * 1024)  # 1MB receive buffer

        while not stop_event.is_set():
            try:
                # If using a buffer becomes too complex, just try to receive
                # and immediately discard smpl_update messages
                response = await asyncio.wait_for(websocket.recv(), timeout=0.1)

                # Quick check if it's an smpl_update before parsing the full JSON
                # Use faster check: check beginning of string
                if response.startswith('{"type":"smpl_update"'):
                    # Skip processing for these messages - no logging here
                    continue # Skip further processing for these messages

                # For all other message types, process normally
                try:
                    response_data = json.loads(response)
                    # Reduced logging level for non-critical responses
                    if response_data.get('type') != 'connection_established': # Avoid logging initial success message again
                         logger.debug(f"Response received: {response_data.get('type')}") # Log only in DEBUG mode
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON response: {response[:200]}...") # Log only a snippet
            except asyncio.TimeoutError:
                # No response within timeout, continue listening
                pass
            except Exception as e:
                # Simplified error checking for closed connections
                if isinstance(e, websockets.exceptions.ConnectionClosed):
                    logger.error(f"Response handler: WebSocket connection closed ({e.code} {e.reason})")
                    stop_event.set()
                    break
                else:
                    # Log other errors but avoid flooding logs
                    if "1001" not in str(e):  # Skip logging normal 'going away' close
                        logger.error(f"Response handler error: {e}")
    except Exception as e:
        logger.error(f"Response handler fatal error: {e}")
        stop_event.set()

async def heartbeat(websocket, stop_event):
    """Send periodic heartbeat to keep connection alive"""
    try:
        while not stop_event.is_set():
            try:
                await websocket.ping()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                stop_event.set()
                break
            await asyncio.sleep(CONFIG['HEARTBEAT_INTERVAL'])
    except Exception as e:
        logger.error(f"Heartbeat fatal error: {e}")
        stop_event.set()

async def send_smpl_pose(websocket, poses, trans, frame_idx=0):
    """Send a single SMPL pose frame to the websocket - non-blocking"""
    try:
        message = {
            "type": "load_pose_smpl",
            "pose": poses[frame_idx],
            "trans": trans[frame_idx],
            "model": "smpl",
            "inference_type": "goal",
            "timestamp": datetime.now().isoformat()
        }
        
        await websocket.send(json.dumps(message))
        return True
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        if "connection is closed" in str(e):
            raise
        return False

async def send_fake_smpl_pose(websocket):
    """Send a test SMPL pose"""
    # Sample pose data
    fake_pose = [0.017441272078737146] * 72  # Simplified for example
    fake_trans = [0.0, 0.0, 0.91437225]
    
    message = {
        "type": "load_pose_smpl",
        "pose": fake_pose,
        "trans": fake_trans,
        "model": "smpl",
        "inference_type": "goal",
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info("Sending fake SMPL pose...")
    await websocket.send(json.dumps(message))
    response = await websocket.recv()
    logger.info(f"Received response: {response}")

async def send_npz_as_smpl(websocket, npz_path, stop_event):
    """Convert and send NPZ animation with frame rate control - non-blocking approach"""
    logger.info(f"Converting NPZ animation: {npz_path}")
    
    smpl_data = convert_npz_to_smpl(npz_path)
    if not smpl_data:
        logger.error("Failed to convert NPZ to SMPL format")
        return
        
    poses = smpl_data['poses']
    trans = smpl_data['trans']
    
    # Get desired FPS from user
    while True:
        try:
            fps_input = input(f"Enter desired frames per second (default: {CONFIG['DEFAULT_FPS']}): ").strip()
            fps = float(fps_input) if fps_input else CONFIG['DEFAULT_FPS']
            if fps > 0:
                break
            print("Please enter a positive number")
        except ValueError:
            print("Invalid input. Please enter a number")
    
    # Calculate which frames to keep
    frame_indices = get_frame_indices(len(poses), fps)
    
    logger.info(f"Original frames: {len(poses)}")
    logger.info(f"Reduced to {len(frame_indices)} frames at {fps} FPS")
    
    # Adjust frame delay based on FPS
    frame_delay = 1.0 / fps
    
    # Track performance metrics
    sent_frames = 0
    dropped_frames = 0
    start_time = time.time()
    
    # Define FPS monitoring function
    def log_performance():
        if sent_frames > 0:
            elapsed = time.time() - start_time
            actual_fps = sent_frames / elapsed if elapsed > 0 else 0
            logger.info(f"Performance: Sent {sent_frames} frames, dropped {dropped_frames}, " 
                      f"actual fps: {actual_fps:.2f}, target: {fps}")
    
    # Schedule periodic performance logging
    performance_log_task = asyncio.create_task(
        asyncio.sleep(5)  # Log after 5 seconds
    )
    
    try:
        for frame_idx in frame_indices:
            if stop_event.is_set():
                logger.info("Stopping animation due to connection issues")
                break
            
            frame_start = time.time()
            
            try:
                logger.debug(f"Sending frame {frame_idx + 1}/{len(poses)}")
                success = await send_smpl_pose(websocket, poses, trans, frame_idx)
                
                if success:
                    sent_frames += 1
                else:
                    dropped_frames += 1
                    logger.warning(f"Failed to send frame {frame_idx + 1}")
                
                # Calculate how long to sleep to maintain target FPS
                elapsed = time.time() - frame_start
                sleep_time = max(0, frame_delay - elapsed)
                
                if elapsed > frame_delay:
                    logger.debug(f"Frame sending took {elapsed:.4f}s, exceeding frame delay of {frame_delay:.4f}s")
                
                await asyncio.sleep(sleep_time)
                
                # Log performance periodically
                if performance_log_task.done():
                    log_performance()
                    performance_log_task = asyncio.create_task(asyncio.sleep(5))
                
            except Exception as e:
                if "connection is closed" in str(e) or "code" in str(e):
                    logger.error(f"WebSocket connection closed while sending frame {frame_idx + 1}: {e}")
                    stop_event.set()
                    break
                else:
                    logger.error(f"Error sending frame {frame_idx + 1}: {e}")
                    dropped_frames += 1
    
    finally:
        # Final performance report
        log_performance()

async def get_current_context(websocket):
    """Request and display current context information"""
    message = {
        "type": "get_current_context",
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info("Requesting current context...")
    await websocket.send(json.dumps(message))
    
    while True:
        response = await websocket.recv()
        
        try:
            context_data = json.loads(response)
            
            # Skip SMPL updates
            if isinstance(context_data, dict) and context_data.get("type") == "smpl_update":
                continue
                
            logger.info("\n=== Current Context Information ===")
            logger.info(json.dumps(context_data, indent=2))
            break
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Raw response: {response}")
            break
        except Exception as e:
            logger.error(f"Error processing response: {e}")
            logger.error(f"Raw response: {response}")
            break

async def load_npz_animation_folder(websocket, folder_path, stop_event):
    """Load and send animations from a folder of NPZ files"""
    try:
        npz_files = [f for f in os.listdir(folder_path) if f.endswith('.npz')]
        if not npz_files:
            logger.info(f"No NPZ files found in folder: {folder_path}")
            return
            
        logger.info(f"Found {len(npz_files)} NPZ files in folder")
        
        for npz_file in npz_files:
            if stop_event.is_set():
                logger.info("Stopping folder processing due to connection issues")
                return

            full_path = os.path.join(folder_path, npz_file)
            logger.info(f"Processing animation: {npz_file}")
            
            await send_npz_as_smpl(websocket, full_path, stop_event)
            
            if npz_file != npz_files[-1] and not stop_event.is_set():
                input("Press Enter to load next animation...")
                
    except FileNotFoundError:
        logger.error(f"Folder not found: {folder_path}")
    except Exception as e:
        logger.error(f"Error loading animations: {e}")

async def trigger_webserver_ai_prompt(prompt=None):
    """Send HTTP POST request to trigger the general AI prompt on the webserver.

    Args:
        prompt (str, optional): A custom prompt text to send. Defaults to None.
    """
    trigger_url = f"{CONFIG['API_URL']}/api/trigger-general-ai-prompt"
    
    payload = {}
    if prompt:
        payload['prompt'] = prompt
        logger.info(f"Sending trigger request to: {trigger_url} with custom prompt")
    else:
        logger.info(f"Sending trigger request to: {trigger_url} (using default prompt)")
        
    try:
        # Use json=payload to automatically set Content-Type: application/json
        response = await asyncio.to_thread(requests.post, trigger_url, json=payload, timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        
        response_data = response.json()
        if response_data.get('success'):
            logger.info(f"AI Prompt trigger sent successfully: {response_data}")
        else:
            logger.error(f"Webserver reported failure: {response_data.get('error')}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP Request failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending the trigger: {e}")

async def start_video_recording(websocket):
    """Send command to start video recording."""
    message = {
        "type": "start_video_recording",
        "timestamp": datetime.now().isoformat()
    }
    logger.info("Sending start video recording command...")
    try:
        await websocket.send(json.dumps(message))
        # Optionally wait for a response confirming start, but keep it simple for now
    except Exception as e:
        logger.error(f"Failed to send start video recording command: {e}")

async def stop_video_recording(websocket):
    """Send command to stop video recording."""
    message = {
        "type": "stop_video_recording",
        "timestamp": datetime.now().isoformat()
    }
    logger.info("Sending stop video recording command...")
    try:
        await websocket.send(json.dumps(message))
        # Optionally wait for confirmation
    except Exception as e:
        logger.error(f"Failed to send stop video recording command: {e}")

async def display_menu():
    """Display the main menu and get user choice"""
    print("\n=== Motivo WebSocket Client Menu ===")
    print("1. Send fake SMPL pose")
    print("2. Get current context")
    print("3. Convert and send NPZ animation")
    print("4. Convert and send NPZ animation folder")
    print("5. Upload NPZ animation to database")
    print("6. Upload NPZ folder to database")
    print("7. Trigger General AI Prompt (via HTTP)")
    print("8. Start Video Recording")
    print("9. Stop Video Recording")
    print("10. Exit")
    
    while True:
        try:
            choice = input("\nEnter your choice (1-10): ")
            if choice in [str(i) for i in range(1, 11)]:
                return choice
            print("Invalid choice. Please enter a number between 1 and 10.")
        except ValueError:
            print("Invalid input. Please enter a number.")

async def establish_connection():
    """Establish WebSocket connection with proper error handling"""
    for retry in range(CONFIG['MAX_RETRIES']):
        try:
            logger.info(f"Connecting to {CONFIG['WS_URI']}...")
            # Add query param to indicate this is a lightweight client
            uri = f"{CONFIG['WS_URI']}?client_type=lightweight"
            websocket = await websockets.connect(uri)
            
            # Wait for the initial connection message
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            response_data = json.loads(response)
            print(response_data)
            
            if response_data.get('type') == 'connection_established':
                logger.info("Connected successfully to simulation WebSocket!")
                return websocket
            else:
                logger.warning(f"Unexpected initial response: {response_data.get('type')}")
                await websocket.close()
        
        except Exception as e:
            logger.error(f"Simulation WebSocket connection attempt {retry+1} failed: {e}")
            if retry < CONFIG['MAX_RETRIES'] - 1:
                wait_time = CONFIG['RETRY_DELAY'] * (retry + 1)
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.error("Failed to establish connection after maximum retries")
                return None
    
    return None

async def interactive_client():
    """Main interactive client with connection management"""
    while True:
        # Establish connection to the simulation WebSocket server (port 8765)
        websocket = await establish_connection()
        if not websocket:
            logger.error("Could not establish simulation WebSocket connection. Exiting.")
            return

        # Set up connection management 
        stop_event = asyncio.Event()
        
        # Start background tasks for connection management
        response_task = asyncio.create_task(response_handler(websocket, stop_event))
        heartbeat_task = asyncio.create_task(heartbeat(websocket, stop_event))
        
        # No separate connection needed for the HTTP trigger
        
        while not stop_event.is_set():
            try:
                choice = await display_menu()
                
                if choice == '1':
                    await send_fake_smpl_pose(websocket)
                elif choice == '2':
                    await get_current_context(websocket)
                elif choice == '3':
                    npz_path = input("\nEnter the path to the NPZ file: ").strip()
                    if npz_path:
                        await send_npz_as_smpl(websocket, npz_path, stop_event)
                elif choice == '4':
                    folder_path = input("\nEnter the path to the NPZ folder: ").strip()
                    if folder_path:
                        await load_npz_animation_folder(websocket, folder_path, stop_event)
                elif choice == '5':
                    npz_path = input("\nEnter the path to the NPZ file: ").strip()
                    users_input = input("\nEnter usernames (comma-separated) or leave empty: ").strip()
                    users = await parse_users_input(users_input)
                    
                    if npz_path:
                        await upload_npz_to_db(npz_path, users)
                elif choice == '6':
                    folder_path = input("\nEnter the path to the NPZ folder: ").strip()
                    users_input = input("\nEnter usernames (comma-separated) or leave empty: ").strip()
                    users = await parse_users_input(users_input)
                    
                    if folder_path:
                        await upload_npz_folder_to_db(folder_path, users)
                elif choice == '7':
                    custom_prompt = None
                    use_custom = input("Use a custom prompt? (y/N): ").strip().lower()
                    if use_custom == 'y':
                        custom_prompt = input("Enter custom prompt text: ").strip()
                        if not custom_prompt:
                            logger.warning("Empty custom prompt entered, using default.")
                            custom_prompt = None
                    await trigger_webserver_ai_prompt(prompt=custom_prompt)
                elif choice == '8':
                    await start_video_recording(websocket)
                elif choice == '9':
                    await stop_video_recording(websocket)
                elif choice == '10':
                    logger.info("Exiting program...")
                    stop_event.set()
                    break
                
                if choice != '10' and not stop_event.is_set():
                    input("\nPress Enter to continue...")
                
            except Exception as e:
                logger.error(f"Operation error: {e}")
                
                # Check if we need to reconnect simulation websocket
                if websocket and websocket.closed:
                     logger.error("Simulation WebSocket connection lost during operation. Attempting to reconnect...")
                     stop_event.set() # Signal background tasks to stop
                     break # Exit inner loop to trigger reconnection in outer loop

        # Clean up tasks for simulation websocket connection
        for task in [response_task, heartbeat_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass # Expected when cancelling
        
        # Close simulation WebSocket if still open
        if websocket and not websocket.closed:
            try:
                await websocket.close()
            except Exception as e:
                logger.warning(f"Error closing simulation websocket: {e}")
        
        # Exit outer loop if user chose to exit
        if choice == '10':
            break
        
        # Otherwise reconnect simulation websocket
        logger.info("Reconnecting simulation WebSocket...")
        await asyncio.sleep(CONFIG['RETRY_DELAY'])

if __name__ == "__main__":
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Connect to Motivo WebSocket and interact.")
    parser.add_argument("--local", action="store_true",
                        help="Use localhost for WebSocket and API connections instead of remote defaults.")
    args = parser.parse_args()

    # --- Update Config based on args ---
    if args.local:
        logger.info("Using --local flag: Connecting to localhost services.")
        CONFIG['WS_URI'] = CONFIG['WS_URI_LOCAL']
        CONFIG['API_URL'] = CONFIG['API_URL_LOCAL']
    else:
        logger.info("Using default remote service addresses.")
        # Keep the default remote URLs already set

    # --- Run the client ---
    # Ensure APIClient is correctly imported and available
    # If APIClient is not used for the POST, ensure 'requests' is installed
    # pip install requests
    try:
        asyncio.run(interactive_client())
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
    except Exception as e:
        logger.error(f"Unexpected error in main execution: {e}")
        import traceback
        traceback.print_exc()