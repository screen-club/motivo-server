import asyncio
import websockets
import logging
import json
import numpy as np
import os
from datetime import datetime
from scipy.spatial.transform import Rotation as R

# Configuration
CONFIG = {
    'WS_URI': 'ws://localhost:8765',
    'MAX_RETRIES': 3,
    'RETRY_DELAY': 2,
    'DEFAULT_FPS': 4,  # Default frames per second
    'FRAME_DELAY': 0.25,  # 1/DEFAULT_FPS
    'RESPONSE_TIMEOUT': 30,
    'HEARTBEAT_INTERVAL': 10
}

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
    # Assuming original animation is 30 FPS
    original_fps = 30
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

async def heartbeat(websocket, stop_event):
    """Send periodic heartbeat to keep connection alive"""
    try:
        while not stop_event.is_set():
            await websocket.ping()
            await asyncio.sleep(CONFIG['HEARTBEAT_INTERVAL'])
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        stop_event.set()

async def send_smpl_pose(websocket, poses, trans, frame_idx=0):
    """Send a single SMPL pose frame to the websocket with timeout"""
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
        response = await asyncio.wait_for(
            websocket.recv(), 
            timeout=CONFIG['RESPONSE_TIMEOUT']
        )
        
        # Validate response
        try:
            response_data = json.loads(response)
            if response_data.get('type') == 'smpl_update':
                return True
            logger.warning(f"Unexpected response type: {response_data.get('type')}")
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON response: {response}")
            
        return True
        
    except asyncio.TimeoutError:
        logger.error("Response timeout")
        raise
    except Exception as e:
        logger.error(f"Send error: {e}")
        raise

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
    """Convert and send NPZ animation with frame rate control"""
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
    
    for frame_idx in frame_indices:
        if stop_event.is_set():
            logger.info("Stopping animation due to connection issues")
            return

        retries = 0
        while retries < CONFIG['MAX_RETRIES']:
            try:
                logger.info(f"Sending frame {frame_idx + 1}/{len(poses)}")
                success = await send_smpl_pose(websocket, poses, trans, frame_idx)
                if success:
                    break
            except Exception as e:
                retries += 1
                if retries == CONFIG['MAX_RETRIES']:
                    logger.error(f"Failed to send frame {frame_idx + 1} after {CONFIG['MAX_RETRIES']} attempts")
                    stop_event.set()
                    return
                logger.info(f"Retry {retries}/{CONFIG['MAX_RETRIES']} after error: {e}")
                await asyncio.sleep(CONFIG['RETRY_DELAY'])
                
        await asyncio.sleep(frame_delay)

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

async def display_menu():
    """Display the main menu and get user choice"""
    print("\n=== Motivo WebSocket Client Menu ===")
    print("1. Send fake SMPL pose")
    print("2. Get current context")
    print("3. Convert and send NPZ animation")
    print("4. Convert and send NPZ animation folder")
    print("5. Exit")
    
    while True:
        try:
            choice = input("\nEnter your choice (1-5): ")
            if choice in ['1', '2', '3', '4', '5']:
                return choice
            print("Invalid choice. Please enter a number between 1 and 5.")
        except ValueError:
            print("Invalid input. Please enter a number.")

async def interactive_client():
    """Main interactive client with connection management"""
    retries = 0
    stop_event = asyncio.Event()
    
    while retries < CONFIG['MAX_RETRIES']:
        try:
            logger.info(f"Connecting to {CONFIG['WS_URI']}...")
            async with websockets.connect(CONFIG['WS_URI']) as websocket:
                logger.info("Connected successfully!")
                
                # Reset stop event for new connection
                stop_event.clear()
                
                # Start heartbeat task
                heartbeat_task = asyncio.create_task(heartbeat(websocket, stop_event))
                
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
                            folder_path = "./npz-animations"
                            await load_npz_animation_folder(websocket, folder_path, stop_event)
                        elif choice == '5':
                            logger.info("Exiting program...")
                            stop_event.set()
                            heartbeat_task.cancel()
                            return
                        
                        if choice != '5' and not stop_event.is_set():
                            input("\nPress Enter to continue...")
                            
                    except websockets.exceptions.WebSocketException as e:
                        logger.error(f"WebSocket error during operation: {e}")
                        stop_event.set()
                        break
                
                # Clean up heartbeat task
                if not heartbeat_task.done():
                    heartbeat_task.cancel()
                        
        except websockets.exceptions.WebSocketException as e:
            retries += 1
            if retries < CONFIG['MAX_RETRIES']:
                logger.error(f"Connection error: {e}")
                logger.info(f"Retrying in {CONFIG['RETRY_DELAY']} seconds... (Attempt {retries}/{CONFIG['MAX_RETRIES']})")
                await asyncio.sleep(CONFIG['RETRY_DELAY'])
                continue
            else:
                logger.error(f"Failed to connect after {CONFIG['MAX_RETRIES']} attempts")
                return
                
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return

if __name__ == "__main__":
    try:
        asyncio.run(interactive_client())
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")