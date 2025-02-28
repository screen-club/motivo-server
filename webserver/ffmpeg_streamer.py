import os
import cv2
import numpy as np
import threading
import subprocess
import time
import logging
import shlex
from typing import Optional, Dict, List, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ffmpeg_streamer')

class FFmpegStreamer:
    """
    A class for streaming video frames using FFmpeg as an alternative to WebRTC.
    Supports multiple streaming protocols including RTMP, HLS, and DASH.
    """
    
    def __init__(self, 
                width: int = 640, 
                height: int = 480, 
                fps: int = 30,
                quality: str = "medium",
                output_dir: str = "stream_output"):
        """
        Initialize the FFmpeg streamer with video settings.
        
        Args:
            width: Video width in pixels
            height: Video height in pixels
            fps: Frames per second
            quality: Quality preset ("medium" or "high")
            output_dir: Directory to store HLS/DASH segments
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = quality
        self.output_dir = output_dir
        self.streaming_process = None
        self.frame_writer_thread = None
        self.is_streaming = False
        self.latest_frame = None
        self.frame_count = 0
        self.stream_type = None
        self.rtmp_url = None
        self.stream_key = None
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "hls"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "dash"), exist_ok=True)
        
        # Quality presets - bitrates in kbps
        self.quality_presets = {
            "medium": {
                "video_bitrate": "2500k",
                "audio_bitrate": "128k",
                "preset": "medium",
                "x264_crf": "23",
            },
            "high": {
                "video_bitrate": "5000k",
                "audio_bitrate": "192k",
                "preset": "medium",  # Using medium for speed/quality balance
                "x264_crf": "18",    # Lower CRF = higher quality
            }
        }
        
        # Use quality preset or default to medium
        self.settings = self.quality_presets.get(quality, self.quality_presets["medium"])
        
        logger.info(f"Initialized FFmpegStreamer with {width}x{height} @ {fps}fps, {quality} quality")
    
    def _get_ffmpeg_env(self) -> Dict[str, str]:
        """Get environment variables for FFmpeg process"""
        env = os.environ.copy()
        
        # Add any needed environment variables
        # env["AV_LOG_FORCE_COLOR"] = "1"  # Force colored logs if needed
        
        return env
    
    def _build_ffmpeg_command(self, stream_type: str) -> List[str]:
        """
        Build the FFmpeg command based on the stream type.
        
        Args:
            stream_type: Type of stream ("rtmp", "hls", or "dash")
            
        Returns:
            List of command arguments for subprocess
        """
        # Common input settings
        cmd = [
            "ffmpeg",
            "-f", "rawvideo",
            "-pixel_format", "rgb24",
            "-video_size", f"{self.width}x{self.height}",
            "-framerate", str(self.fps),
            "-i", "pipe:",  # Read from stdin
        ]
        
        # Add fake audio if needed (silent)
        # cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
        
        # Video codec settings
        cmd.extend([
            "-c:v", "libx264",
            "-preset", self.settings["preset"],
            "-crf", self.settings["x264_crf"],
            "-b:v", self.settings["video_bitrate"],
            "-maxrate", str(int(self.settings["video_bitrate"].replace("k", "")) * 1.5) + "k",
            "-bufsize", str(int(self.settings["video_bitrate"].replace("k", "")) * 2) + "k",
            "-pix_fmt", "yuv420p",  # Broadly compatible pixel format
            "-g", str(self.fps * 2),  # GOP size (2 seconds)
            "-keyint_min", str(self.fps),  # Minimum GOP size (1 second)
            "-sc_threshold", "0",  # Disable scene change detection for consistent bitrate
            "-profile:v", "high",  # High profile for better quality
            "-level", "4.1",       # Compatibility level
        ])
        
        # No audio for simplicity
        cmd.extend(["-an"])
        
        # Output settings based on stream type
        if stream_type == "rtmp":
            if not self.rtmp_url:
                raise ValueError("RTMP URL not set")
                
            # RTMP output
            cmd.extend([
                "-f", "flv",
                "-flvflags", "no_duration_filesize",  # Don't write duration and filesize
                self.rtmp_url,
            ])
            
        elif stream_type == "hls":
            # HLS output
            hls_path = os.path.join(self.output_dir, "hls", "stream.m3u8")
            cmd.extend([
                "-f", "hls",
                "-hls_time", "2",  # Segment duration
                "-hls_list_size", "10",  # Number of segments to keep
                "-hls_flags", "delete_segments+append_list+discont_start",
                "-hls_segment_type", "mpegts",
                "-hls_segment_filename", os.path.join(self.output_dir, "hls", "segment_%d.ts"),
                hls_path,
            ])
            
        elif stream_type == "dash":
            # DASH output
            dash_path = os.path.join(self.output_dir, "dash", "stream.mpd")
            cmd.extend([
                "-f", "dash",
                "-dash_segment_type", "mp4",
                "-use_template", "1",
                "-use_timeline", "1",
                "-seg_duration", "2",  # Segment duration
                "-window_size", "10",  # Number of segments to keep
                dash_path,
            ])
            
        else:
            raise ValueError(f"Unsupported stream type: {stream_type}")
            
        # Add logging level
        cmd.extend(["-loglevel", "warning"])
        
        return cmd
    
    def set_rtmp_url(self, rtmp_url: str, stream_key: Optional[str] = None):
        """
        Set the RTMP URL and stream key for RTMP streaming.
        
        Args:
            rtmp_url: RTMP server URL (e.g. rtmp://live.twitch.tv/app)
            stream_key: Stream key (will be appended to URL if provided)
        """
        if stream_key:
            self.rtmp_url = f"{rtmp_url}/{stream_key}"
        else:
            self.rtmp_url = rtmp_url
            
        self.stream_key = stream_key
        logger.info(f"RTMP URL set to: {self.rtmp_url}")
    
    def update_frame(self, frame):
        """
        Update the current frame to be streamed.
        
        Args:
            frame: OpenCV/numpy image in BGR format
        """
        try:
            if frame is None:
                logger.warning("Received None frame, skipping")
                return
                
            # Convert BGR to RGB (FFmpeg expects RGB)
            if frame.shape[2] == 3:
                processed_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                processed_frame = frame
                
            # Resize if needed
            if processed_frame.shape[1] != self.width or processed_frame.shape[0] != self.height:
                processed_frame = cv2.resize(
                    processed_frame,
                    (self.width, self.height),
                    interpolation=cv2.INTER_LANCZOS4
                )
                
            # Store the frame
            self.latest_frame = processed_frame
            self.frame_count += 1
            
            # Log occasionally
            if self.frame_count % 100 == 0:
                logger.info(f"Processed {self.frame_count} frames")
                
        except Exception as e:
            logger.error(f"Error updating frame: {str(e)}")
    
    def _frame_writer(self):
        """Background thread that writes frames to FFmpeg process"""
        logger.info("Frame writer thread started")
        
        try:
            while self.is_streaming and self.streaming_process:
                if self.latest_frame is not None:
                    # Write frame data to FFmpeg's stdin
                    frame_data = self.latest_frame.tobytes()
                    self.streaming_process.stdin.write(frame_data)
                    self.streaming_process.stdin.flush()
                    
                # Limit the frame rate
                time.sleep(1 / self.fps)
                
        except (BrokenPipeError, IOError) as e:
            logger.error(f"Pipe error in frame writer: {str(e)}")
        except Exception as e:
            logger.error(f"Error in frame writer thread: {str(e)}")
        finally:
            logger.info("Frame writer thread stopping")
            
            # Try to close stdin if it's still open
            try:
                if self.streaming_process and self.streaming_process.stdin:
                    self.streaming_process.stdin.close()
            except:
                pass
                
            self.is_streaming = False
    
    def start_streaming(self, stream_type: str = "hls") -> Dict[str, str]:
        """
        Start streaming video frames.
        
        Args:
            stream_type: Type of stream ("rtmp", "hls", or "dash")
            
        Returns:
            Dict with stream URLs and information
        """
        if self.is_streaming:
            logger.warning("Streaming is already active, stopping first")
            self.stop_streaming()
            
        self.stream_type = stream_type
        self.is_streaming = True
        
        try:
            # Build FFmpeg command
            cmd = self._build_ffmpeg_command(stream_type)
            cmd_str = ' '.join([shlex.quote(str(arg)) for arg in cmd])
            logger.info(f"Starting FFmpeg with command: {cmd_str}")
            
            # Start FFmpeg process
            self.streaming_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._get_ffmpeg_env(),
                bufsize=10 * self.width * self.height * 3  # Buffer 10 frames
            )
            
            # Start frame writer thread
            self.frame_writer_thread = threading.Thread(target=self._frame_writer)
            self.frame_writer_thread.daemon = True
            self.frame_writer_thread.start()
            
            # Provide URLs based on stream type
            stream_info = {"stream_type": stream_type}
            
            if stream_type == "rtmp":
                stream_info["url"] = self.rtmp_url
                if self.stream_key:
                    stream_info["stream_key"] = self.stream_key
                
            elif stream_type == "hls":
                base_url = "/stream/hls/stream.m3u8"  # Relative URL, can be changed
                stream_info["url"] = base_url
                stream_info["file_path"] = os.path.join(self.output_dir, "hls", "stream.m3u8")
                
            elif stream_type == "dash":
                base_url = "/stream/dash/stream.mpd"  # Relative URL, can be changed
                stream_info["url"] = base_url
                stream_info["file_path"] = os.path.join(self.output_dir, "dash", "stream.mpd")
            
            logger.info(f"Streaming started with {stream_type}, info: {stream_info}")
            return stream_info
            
        except Exception as e:
            logger.error(f"Error starting streaming: {str(e)}")
            self.is_streaming = False
            if self.streaming_process:
                try:
                    self.streaming_process.terminate()
                except:
                    pass
                self.streaming_process = None
            raise
    
    def stop_streaming(self):
        """Stop streaming and clean up resources"""
        logger.info("Stopping streaming")
        self.is_streaming = False
        
        # Wait for frame writer thread to finish
        if self.frame_writer_thread and self.frame_writer_thread.is_alive():
            self.frame_writer_thread.join(timeout=2.0)
        
        # Terminate FFmpeg process
        if self.streaming_process:
            try:
                # Try graceful shutdown first
                if self.streaming_process.stdin:
                    self.streaming_process.stdin.close()
                    
                # Give it a moment to close gracefully
                for _ in range(10):
                    if self.streaming_process.poll() is not None:
                        break
                    time.sleep(0.1)
                    
                # Force terminate if still running
                if self.streaming_process.poll() is None:
                    self.streaming_process.terminate()
                    time.sleep(0.5)
                    
                # Kill if still not dead
                if self.streaming_process.poll() is None:
                    self.streaming_process.kill()
                    
            except Exception as e:
                logger.error(f"Error stopping FFmpeg process: {str(e)}")
                
            self.streaming_process = None
            
        logger.info("Streaming stopped")
    
    def get_streaming_status(self) -> Dict[str, Any]:
        """Get current streaming status information"""
        status = {
            "is_streaming": self.is_streaming,
            "stream_type": self.stream_type,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "quality": self.quality,
            "frame_count": self.frame_count,
        }
        
        # Add stream-type specific info
        if self.stream_type == "rtmp":
            status["rtmp_url"] = self.rtmp_url
        
        # Add process status
        if self.streaming_process:
            status["process_alive"] = self.streaming_process.poll() is None
            
        return status
    
    def set_quality(self, quality: str) -> bool:
        """
        Change streaming quality.
        
        Args:
            quality: Quality preset name ("medium" or "high")
            
        Returns:
            True if successful, False otherwise
        """
        if quality not in self.quality_presets:
            logger.error(f"Unknown quality preset: {quality}")
            return False
            
        # If streaming is active, need to restart the stream
        was_streaming = self.is_streaming
        stream_type = self.stream_type
        
        if was_streaming:
            self.stop_streaming()
            
        # Update settings
        self.quality = quality
        self.settings = self.quality_presets[quality]
        logger.info(f"Quality set to {quality}: {self.settings}")
        
        # Restart if it was streaming
        if was_streaming and stream_type:
            self.start_streaming(stream_type)
            
        return True 