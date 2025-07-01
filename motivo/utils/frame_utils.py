import os
import cv2
import numpy as np
import json
import pickle
from datetime import datetime
from utils.smpl_utils import qpos_to_smpl, SMPL_BONE_ORDER_NAMES
import zipfile
import logging
import asyncio
import concurrent.futures
import subprocess

logger = logging.getLogger('frame_utils')

def save_frame_data(frame, qpos, qvel, env=None, smpl_data=None):
    """
    Save current frame image and state data with bone ordering information
    """
    # Get config for paths
    from core.config import config
    
    # Create output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(config.captured_frames_dir, timestamp)
    os.makedirs(output_dir, exist_ok=True)
    
    # Save image
    image_path = os.path.join(output_dir, "frame.png")
    cv2.imwrite(image_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    
    # Convert to SMPL if environment is provided and smpl_data is not
    if env is not None and smpl_data is None:
        pose, trans = qpos_to_smpl(qpos, env.unwrapped.model)
        smpl_data = {
            'poses': pose,
            'trans': trans[0],
            'betas': None
        }
    
    # Save state data as NPZ (for numerical data)
    npz_data = {
        'qpos': qpos,
        'qvel': qvel,
        'timestamp': timestamp
    }
    if smpl_data:
        npz_data.update(smpl_data)
    
    data_path = os.path.join(output_dir, "state_data.npz")
    np.savez(data_path, **npz_data)
    
    # Save SMPL data as pickle if available
    if smpl_data:
        # Get poses and ensure correct shape (frames, joints*3)
        poses = smpl_data['poses']
        
        # Debug print before reshaping
        print(f"Original poses shape: {poses.shape}")
        
        # If poses is 1D (72 values), reshape to (1, 72)
        if len(poses.shape) == 1 and poses.shape[0] == 72:
            print("Case 1: Converting 1D poses (72) to (1, 72)")
            poses = poses.reshape(1, 72)
        # If poses is 3D (batch, 24, 3), reshape to (batch, 72)
        elif len(poses.shape) == 3 and poses.shape[1:] == (24, 3):
            print("Case 2: Converting 3D poses (batch, 24, 3) to (batch, 72)")
            poses = poses.reshape(poses.shape[0], 72)
        # If poses is already 2D (batch, 72), keep as is
        elif len(poses.shape) == 2 and poses.shape[1] == 72:
            print("Case 3: Poses already in correct format (batch, 72)")
            poses = poses
        else:
            print(f"ERROR: Unhandled pose shape: {poses.shape}")
            raise ValueError(f"Unexpected poses shape: {poses.shape}")
            
        # Debug print after reshaping
        print(f"Final poses shape: {poses.shape}")
            
        pkl_data = {
            'smpl_poses': poses,  # Will be shape (frames, 72)
            'smpl_trans': smpl_data['trans'][np.newaxis, :] if isinstance(smpl_data['trans'], np.ndarray) else np.array([smpl_data['trans']])
        }
        
        pkl_path = os.path.join(output_dir, "smpl_data.pkl")
        with open(pkl_path, 'wb') as f:
            pickle.dump(pkl_data, f)
    
    # Create metadata JSON
    metadata = {
        'metadata': {
            'timestamp': timestamp,
            'format_version': '1.0',
            'description': 'Humanoid pose capture data'
        },
        'bone_hierarchy': {
            'order': SMPL_BONE_ORDER_NAMES,
            'root': 'Pelvis',
            'description': 'Bone order for pose reconstruction'
        },
        'data_format': {
            'qpos': {
                'description': 'MuJoCo joint positions',
                'shape': list(qpos.shape),
                'dtype': str(qpos.dtype)
            },
            'qvel': {
                'description': 'MuJoCo joint velocities',
                'shape': list(qvel.shape),
                'dtype': str(qvel.dtype)
            }
        },
        'image': {
            'path': 'frame.png',
            'format': 'PNG',
            'colorspace': 'RGB'
        }
    }
    
    # Add SMPL format info if available
    if smpl_data:
        metadata['smpl_format'] = {
            'description': 'SMPL pose parameters',
            'poses': {
                'shape': list(smpl_data['poses'].shape),
                'dtype': str(smpl_data['poses'].dtype),
                'format': 'rotation vectors (radians)',
                'bone_order': SMPL_BONE_ORDER_NAMES
            },
            'translation': {
                'description': 'Root translation relative to Pelvis',
                'format': 'XYZ coordinates'
            }
        }
    
    # Create separate data JSON
    pose_data = {
        'timestamp': timestamp,
        'qpos': qpos.tolist(),
        'qvel': qvel.tolist()
    }
    
    if smpl_data:
        pose_data['smpl'] = {
            'poses': smpl_data['poses'].tolist(),
            'translation': smpl_data['trans'].tolist() if isinstance(smpl_data['trans'], np.ndarray) else smpl_data['trans']
        }
    
    # Save both JSON files
    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
        
    data_path = os.path.join(output_dir, "pose_data.json")
    with open(data_path, 'w') as f:
        json.dump(pose_data, f, indent=2)
    
    print(f"Saved frame and state data to: {output_dir}")

def save_shared_frame(frame, resize_width=640):
    """Save a frame to the shared_frames directory for use by the webserver
    
    Args:
        frame: RGB image array
        resize_width: Width to resize the image to (preserves aspect ratio)
    
    Returns:
        Path to the saved frame
    """
    from core.config import config
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(config.shared_frames_dir, exist_ok=True)
        
        # Resize image while preserving aspect ratio
        h, w = frame.shape[:2]
        aspect_ratio = h / w
        new_width = resize_width
        new_height = int(new_width * aspect_ratio)
        
        # Resize the image
        resized_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # Convert RGB to BGR for OpenCV
        bgr_frame = cv2.cvtColor(resized_frame, cv2.COLOR_RGB2BGR)
        
        # Generate a unique timestamp-based filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        unique_filename = f"frame_{timestamp}.jpg"
        
        # Save image with unique filename
        frame_path = os.path.join(config.shared_frames_dir, unique_filename)
        cv2.imwrite(frame_path, bgr_frame)
        
        # Also save as latest_frame.jpg for backwards compatibility
        latest_frame_path = os.path.join(config.shared_frames_dir, 'latest_frame.jpg')
        cv2.imwrite(latest_frame_path, bgr_frame)
        
        # Save timestamp
        timestamp_path = os.path.join(config.shared_frames_dir, 'timestamp.txt')
        with open(timestamp_path, 'w') as f:
            f.write(datetime.now().isoformat())
        
        # Cleanup old files, keeping only the 30 most recent ones
        cleanup_old_frames(config.shared_frames_dir, max_files=30)
        
        logger.info(f"Saved shared frame: {frame_path} ({new_width}x{new_height})")
        return frame_path
    
    except Exception as e:
        logger.error(f"Error saving shared frame: {str(e)}")
        return None

def cleanup_old_frames(directory, max_files=30):
    """Cleanup old frame files, keeping only the most recent ones
    
    Args:
        directory: Directory containing frame files
        max_files: Maximum number of files to keep (excluding latest_frame.jpg and timestamp.txt)
    """
    try:
        # Get all jpg files except latest_frame.jpg
        files = [os.path.join(directory, f) for f in os.listdir(directory) 
                if f.endswith('.jpg') and f != 'latest_frame.jpg']
        
        # Sort files by modification time (oldest first)
        files.sort(key=os.path.getmtime)
        
        # Remove oldest files if we have too many
        files_to_remove = len(files) - max_files
        if files_to_remove > 0:
            for i in range(files_to_remove):
                if i < len(files):  # Safety check
                    os.remove(files[i])
                    logger.info(f"Removed old frame: {files[i]}")
    
    except Exception as e:
        logger.error(f"Error cleaning up old frames: {str(e)}")
        # Don't raise exception - this is a maintenance operation that shouldn't break the main function

class FrameRecorder:
    def __init__(self):
        self.frames_data = [] # List of {timestamp, pose, trans} dicts
        self.recording = False

    def record_frame_data(self, frame_image, qpos, qvel, env_unwrapped):
        """
        Records a minimal set of SMPL parameters (pose, trans) for each frame,
        matching the core of the live stream.
        env_unwrapped must be the MuJoCo environment instance with the .model attribute.
        frame_image and qvel are currently unused here.
        """
        if not self.recording:
            return

        try:
            # qpos_to_smpl returns: pose (np), trans (np), positions (list of np), position_names (list of str)
            # We only need pose and trans for the PKL as per user request.
            smpl_pose, smpl_trans, _, _ = qpos_to_smpl(qpos, env_unwrapped.model)

            frame_state = {
                'timestamp': datetime.now().isoformat(),
                'pose': smpl_pose,    # NumPy array (e.g., BxNx3 or Nx3 for axis-angle)
                'trans': smpl_trans,  # NumPy array (e.g., Bx3 or 1x3 or 3,)
            }
            self.frames_data.append(frame_state)

        except Exception as e:
            logger.error(f"Error in FrameRecorder.record_frame_data during SMPL conversion: {e}")
            # Minimal fallback if conversion fails
            self.frames_data.append({
                'timestamp': datetime.now().isoformat(),
                'error': 'SMPL conversion failed for this frame.',
                'raw_qpos': qpos.copy() # Optionally store raw qpos on error
            })

    def get_recorded_data_for_manual_zipping(self):
        """
        Returns a list of state dictionaries (timestamp, pose, trans) for pickling.
        Clears internal frames_data after returning data.
        """
        if not self.frames_data:
            logger.debug("FrameRecorder.get_recorded_data_for_manual_zipping: No frame data.")
            return [] 
            
        data_to_return = list(self.frames_data) 
        self.recording = False
        self.frames_data = []
        logger.debug(f"Extracted {len(data_to_return)} states (timestamp, pose, trans) for packaging.")
        return data_to_return

    def end_record(self, output_path=None):
        """
        Saves trajectory data (list of {timestamp, pose, trans}) as a .pkl file.
        (Handles .zip or direct .pkl output based on output_path extension, as before)
        """
        if not self.frames_data:
            logger.warning("FrameRecorder.end_record called with no frame data recorded.")
            self.recording = False
            return None 

        is_zip_output = output_path and output_path.lower().endswith(".zip")
        is_pkl_output = output_path and output_path.lower().endswith(".pkl")
        parent_dir_exists = output_path and os.path.exists(os.path.dirname(output_path))
        has_no_common_archive_extension = output_path and not (is_zip_output or is_pkl_output)
        is_intended_as_dir = output_path and parent_dir_exists and has_no_common_archive_extension and (not os.path.splitext(output_path)[1])
        pkl_content_name = "smpl_trajectory_data.pkl"

        if not output_path: 
            from core.config import config 
            output_path = os.path.join(config.downloads_dir, pkl_content_name)
            os.makedirs(config.downloads_dir, exist_ok=True)
            is_pkl_output = True
        elif is_intended_as_dir:
             os.makedirs(output_path, exist_ok=True)
             output_path = os.path.join(output_path, pkl_content_name)
             is_pkl_output = True
        else:
            # Ensure directory for a specific file path exists
            if os.path.dirname(output_path): # Check if there is a directory part
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
            elif not output_path: # Should be caught by the first if, but as a safeguard
                logger.error("end_record: output_path became empty, cannot proceed.")
                return None

        try:
            if is_zip_output:
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    pickled_data = pickle.dumps(self.frames_data)
                    zf.writestr(pkl_content_name, pickled_data)
                logger.info(f"SMPL trajectory data (pose, trans) saved to '{pkl_content_name}' inside zip: {output_path}")
            elif is_pkl_output:
                with open(output_path, 'wb') as f:
                    pickle.dump(self.frames_data, f)
                logger.info(f"SMPL trajectory data (pose, trans) saved directly to PKL file: {output_path}")
        except Exception as e:
            logger.error(f"Error saving SMPL trajectory data (pose, trans) to {output_path}: {e}")
            self.recording = False; self.frames_data = []; return None
        
        self.recording = False
        self.frames_data = []
        return output_path

class VideoRecorder:
    """Records frames to a video file using OpenCV asynchronously."""
    def __init__(self, output_path, fps, width, height):
        self.output_path = output_path
        self.fps = float(fps)
        self.width = int(width)
        self.height = int(height)
        self.writer = None
        self.recording = False
        self._frame_count = 0
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.loop = asyncio.get_running_loop()
        self._pending_writes = []

        # Get the directory part of the output path
        output_dir = os.path.dirname(self.output_path)
        # Create the directory if it doesn't exist
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Define the codec and create VideoWriter object
        # H264 is the most web-compatible codec for MP4 files
        # Try multiple codecs in order of preference and compatibility
        codecs_to_try = [
            ('avc1', 'H.264 (AVC1) - Most widely supported web format'),
            ('h264', 'H.264 - Widely supported on the web'),
            ('mp4v', 'MPEG-4 - Fallback option')
        ]
        
        # Try each codec in order until one works
        for codec, codec_name in codecs_to_try:
            try:
                logger.info(f"Trying video codec: {codec} ({codec_name})")
                fourcc = cv2.VideoWriter_fourcc(*codec)
                self.writer = cv2.VideoWriter(
                    self.output_path, 
                    fourcc, 
                    self.fps, 
                    (self.width, self.height)
                )
                
                if self.writer.isOpened():
                    logger.info(f"VideoWriter initialized with codec {codec} for {self.output_path} at {self.fps} FPS, {self.width}x{self.height}")
                    break
                else:
                    logger.warning(f"Codec {codec} failed to open writer, trying next option")
                    self.writer = None
            except Exception as e:
                logger.warning(f"Failed to initialize VideoWriter with codec {codec}: {e}")
                self.writer = None
        
        if self.writer is None:
            error_msg = f"Failed to initialize VideoWriter with any codec for path: {self.output_path}"
            logger.error(error_msg)
            raise IOError(error_msg)

    def start(self):
        """Marks the recorder as active."""
        if self.writer is None:
            logger.error("Cannot start recording, VideoWriter not initialized.")
            return
        self.recording = True
        self._frame_count = 0
        logger.info("Video recording started.")

    async def add_frame(self, frame: np.ndarray):
        """Adds a frame to the video file asynchronously.

        Args:
            frame: The frame to add (expected in RGB format).
        """
        if not self.recording or self.writer is None:
            return

        try:
            # --- Operations safe for async context ---
            # Ensure frame dimensions match
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                # Make a copy before resizing if needed to avoid modifying original
                frame_copy = frame.copy()
                frame_to_write = cv2.resize(frame_copy, (self.width, self.height))
                # logger.warning(f"Resized incoming frame from {frame.shape[1]}x{frame.shape[0]} to {self.width}x{self.height}")
            else:
                # Make a copy to ensure the frame data is stable when passed to the thread
                frame_to_write = frame.copy()

            # Convert RGB frame to BGR for OpenCV
            #bgr_frame = cv2.cvtColor(frame_to_write, cv2.COLOR_RGB2BGR)
            self._frame_count += 1 # Increment frame count immediately
            current_frame_num = self._frame_count # Store for logging

            # --- Offload the blocking write operation --- 
            write_task = self.loop.run_in_executor(
                self.executor, 
                self._write_frame_sync, # Call a synchronous wrapper
                frame_to_write, 
                current_frame_num
            )
            self._pending_writes.append(write_task)
            
            # Periodically clean up completed tasks to prevent memory leak
            if len(self._pending_writes) > self.fps * 2: # Clean up every ~2 seconds
                 self._pending_writes = [task for task in self._pending_writes if not task.done()]

        except Exception as e:
            logger.error(f"Error preparing frame {self._frame_count} for video write: {e}")
            # Optionally stop recording on error?
            # await self.stop()

    def _write_frame_sync(self, frame, frame_num):
        """Synchronous helper function to be run in the executor."""
        try:
            if self.writer and self.writer.isOpened():
                # Input frame is RGB but OpenCV requires BGR for video writing
                bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                self.writer.write(bgr_frame)
            else:
                logger.warning(f"Skipped writing frame {frame_num}, writer is closed or None.")
        except Exception as e:
            logger.error(f"Error writing frame {frame_num} to video in thread: {e}")

    async def stop(self):
        """Stops recording, waits for pending writes, and releases the video writer."""
        if not self.recording:
            return

        logger.info("Stop recording requested. Waiting for pending writes...")
        self.recording = False # Signal that no more frames should be added
        original_path = self.output_path

        # Wait for all submitted write tasks to complete
        if self._pending_writes:
            try:
                await asyncio.gather(*self._pending_writes)
                logger.info(f"All {len(self._pending_writes)} pending writes completed.")
            except Exception as e:
                logger.error(f"Error waiting for pending writes: {e}")
            finally:
                 self._pending_writes = [] # Clear the list

        # Shutdown the executor gracefully
        # Do this *before* releasing the writer to ensure writes are done
        logger.info("Shutting down video writer executor...")
        try:
            # Create a callable that will shutdown the executor with wait=True
            def shutdown_executor():
                self.executor.shutdown(wait=True)
                return True
                
            # Execute the callable in the default executor
            await self.loop.run_in_executor(None, shutdown_executor)
            logger.info("Video writer executor shut down.")
        except Exception as e:
            logger.error(f"Error shutting down executor: {e}")
            # Try direct shutdown as fallback
            self.executor.shutdown(wait=False)

        # Now release the writer
        if self.writer is not None:
            try:
                # This is synchronous, run in executor just in case it blocks
                await self.loop.run_in_executor(None, self.writer.release)
                logger.info(f"Video recording stopped. Approximately {self._frame_count} frames saved to {self.output_path}")
                
                # Post-process the video to ensure web compatibility
                web_compatible = await self._ensure_web_compatible_format()
                
                if web_compatible:
                    logger.info(f"Video successfully processed for web compatibility: {self.output_path}")
                else:
                    logger.warning(f"Could not optimize video for web compatibility. Using original format: {self.output_path}")
            except Exception as e:
                 logger.error(f"Error releasing video writer: {e}")
            finally:
                self.writer = None
        else:
             logger.warning("Stop called but VideoWriter was not initialized or already released.")
        
        self._frame_count = 0 # Reset frame count after stopping
        
        # Return the final path (which may be different after optimization)
        return self.output_path
    
    async def _ensure_web_compatible_format(self):
        """Attempts to ensure the video is in a web-compatible format using FFmpeg if available."""
        try:
            # Check if ffmpeg is available (with different commands for different OS)
            if os.name == 'nt':  # Windows
                check_cmd = ["where", "ffmpeg"]
            else:  # Unix/Linux/Mac
                check_cmd = ["which", "ffmpeg"]
                
            result = await self.loop.run_in_executor(None, lambda: subprocess.run(
                check_cmd, 
                capture_output=True, 
                text=True
            ))
            
            # If FFmpeg is not available, try to continue with OpenCV output
            if result.returncode != 0:
                logger.info("FFmpeg not found, skipping web compatibility optimization")
                return False
                
            # FFmpeg is available, create a temporary output path
            original_path = self.output_path
            output_path_parts = os.path.splitext(original_path)
            temp_path = f"{output_path_parts[0]}_web{output_path_parts[1]}"
            
            # Use FFmpeg to convert the video to a web-compatible format
            logger.info(f"Using FFmpeg to optimize video for web compatibility: {original_path} -> {temp_path}")
            
            # Run FFmpeg with settings for web compatibility
            # -movflags faststart moves metadata to the beginning of the file for faster web playback
            # -c:v libx264 uses the h264 codec
            # -profile:v baseline is the most compatible h264 profile
            # -level 3.0 is widely supported
            # -pix_fmt yuv420p ensures pixel format compatibility
            cmd = [
                "ffmpeg", "-y", "-i", original_path,
                "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
                "-pix_fmt", "yuv420p", "-crf", "23", 
                "-movflags", "+faststart", 
                temp_path
            ]
            
            # Run FFmpeg and capture output for debugging
            try:
                process = await self.loop.run_in_executor(None, lambda: subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True,
                    check=False  # Don't raise exception on non-zero exit
                ))
                
                if process.returncode == 0:
                    logger.info("FFmpeg conversion successful")
                    
                    # Check that output file exists and has size > 0
                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                        # Replace original file with web-optimized version
                        await self.loop.run_in_executor(None, lambda: os.rename(temp_path, original_path))
                        logger.info(f"Successfully replaced original with web-compatible version")
                        return True
                    else:
                        logger.warning(f"FFmpeg output file missing or empty: {temp_path}")
                        return False
                else:
                    logger.warning(f"FFmpeg conversion failed with code {process.returncode}: {process.stderr}")
                    # Keep the original file
                    return False
            except Exception as ffmpeg_err:
                logger.error(f"FFmpeg process error: {ffmpeg_err}")
                return False
                
        except Exception as e:
            logger.error(f"Error ensuring web compatibility: {e}")
            return False

    def __del__(self):
        # Attempt graceful shutdown if stop() wasn't called explicitly
        # Note: Running async code in __del__ is generally problematic.
        # Explicitly calling stop() is the preferred way.
        if self.recording:
             logger.warning(f"VideoRecorder for {self.output_path} being deleted while still recording. Attempting emergency stop.")
             # Cannot reliably call async stop here. Rely on writer release.
             self.recording = False 

        if self.writer is not None and self.writer.isOpened():
            logger.warning(f"VideoRecorder releasing writer during garbage collection for {self.output_path}")
            self.writer.release()
        
        # Executor shutdown might be problematic here. Best effort.
        if hasattr(self, 'executor') and self.executor._shutdown == False:
             logger.warning(f"VideoRecorder shutting down executor during garbage collection for {self.output_path}")
             try:
                  self.executor.shutdown(wait=False) # Don't wait in __del__
             except Exception as e:
                  logger.error(f"Error shutting down executor in __del__: {e}") 