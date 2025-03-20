import os
import cv2
import numpy as np
import threading
import subprocess
import time
import logging
import shlex
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('streaming_service')

class FFmpegStreamer:
    """
    A class for streaming video frames using FFmpeg as an alternative to WebRTC.
    Supports multiple streaming protocols including RTMP, HLS, and DASH.
    """
    
    def __init__(self, output_dir: str = None, width: int = 640, height: int = 480, fps: int = 30):
        """
        Initialize the FFmpeg streamer.
        
        Args:
            output_dir: Directory to store streaming output files
            width: Width of the video stream
            height: Height of the video stream
            fps: Frames per second of the video stream
        """
        # Get path to public storage
        self.base_dir = str(Path(__file__).resolve().parents[3])
        
        # Use output_dir if provided, otherwise create a default location
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = os.path.join(self.base_dir, 'public', 'storage', 'streams')
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Video settings
        self.width = width
        self.height = height
        self.fps = fps
        
        # FFmpeg processes
        self.ffmpeg_processes: Dict[str, subprocess.Popen] = {}
        
        # Stream state
        self.is_streaming = False
        self.stream_thread = None
        self.stop_event = threading.Event()
        
        # Active stream formats
        self.active_formats: Dict[str, Dict] = {}
        
        logger.info(f"FFmpegStreamer initialized with output directory: {self.output_dir}")
        logger.info(f"Video settings: {width}x{height} @ {fps}fps")