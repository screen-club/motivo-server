import os
import json
from pathlib import Path

# Determine the project root directory based on the location of this config.py file
# __file__ is motivo/core/config.py
# os.path.dirname(__file__) is motivo/core/
# os.path.dirname(os.path.dirname(__file__)) is motivo/
# os.path.dirname(os.path.dirname(os.path.dirname(__file__))) is the project root (e.g., motivo-server/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

class Config:
    """Centralized configuration management"""
    
    def __init__(self):
        # Server config
        self.backend_domain = os.getenv("VITE_BACKEND_DOMAIN", "localhost")
        self.ws_port = int(os.getenv("VITE_WS_PORT", 8765))
        self.api_port = int(os.getenv("VITE_API_PORT", 5000))
        self.webserver_port = int(os.getenv("VITE_WEBSERVER_PORT", 5002))
        
        # Model config
        self.default_model = "metamotivo-M-1"
        
        # Base paths - now robustly defined relative to PROJECT_ROOT
        self.project_root_dir = PROJECT_ROOT # For clarity if needed elsewhere
        self.storage_dir = os.path.join(PROJECT_ROOT, 'storage')
        self.public_dir = os.path.join(PROJECT_ROOT, 'public') # Corrected
        self.motivo_internal_dir = os.path.join(PROJECT_ROOT, 'motivo') # For things inside 'motivo' folder

        # Derived paths
        self.cache_dir = os.path.join(self.storage_dir, 'model') # storage/model/
        
        # Corrected shared_frames_dir to be directly under PROJECT_ROOT/public/
        self.shared_frames_dir = os.path.join(self.public_dir, 'shared_frames') 
        self.gemini_frame_path = os.path.join(self.shared_frames_dir, 'latest_frame.jpg')
        
        self.captured_frames_dir = os.path.join(self.storage_dir, 'captured_frames') # storage/captured_frames/
        
        # CRITICAL CHANGE: downloads_dir now points to PROJECT_ROOT/motivo/downloads/
        # This aligns with where webserver.py expects to find packages.
        self.downloads_dir = os.path.join(self.motivo_internal_dir, 'downloads') 
        
        self.videos_dir = os.path.join(self.storage_dir, 'videos') # storage/videos/
        
        # For files that might be copied to a web-accessible public location by the webserver or other processes
        self.web_accessible_storage_dir = os.path.join(self.public_dir, 'storage') # public/storage/
        self.public_videos_dir = os.path.join(self.web_accessible_storage_dir, 'videos') # public/storage/videos/
        
        # Create all necessary directories using these absolute paths
        os.makedirs(self.shared_frames_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.captured_frames_dir, exist_ok=True)
        os.makedirs(self.downloads_dir, exist_ok=True) # Now PROJECT_ROOT/motivo/downloads/
        os.makedirs(self.videos_dir, exist_ok=True)     # Now PROJECT_ROOT/storage/videos/
        os.makedirs(self.public_videos_dir, exist_ok=True)
        
        # Runtime config
        self.debug = os.getenv("MOTIVO_DEBUG", "0") == "1"
        self.in_container = os.path.exists('/.dockerenv') or os.environ.get('ENVIRONMENT') == 'production'
        
        # Set target FPS - use environment variable if provided, otherwise default to 60
        # User wants 60 FPS for simulation, SMPL data, and video.
        self.fps = int(os.getenv("MOTIVO_FPS", "60"))
        
        # Default reward configuration
        self.default_reward_config = {
            'rewards': [
                { 'name': 'move-ego', 'move_speed': 0.0, 'stand_height': 1.4 }
            ],
            'weights': [1.0]
        }
        
        # Video settings - default to "low" for stability
        self.default_video_quality = os.getenv("MOTIVO_VIDEO_QUALITY", "low")
        self.video_qualities = ["low", "medium", "high", "hd"]
        
    @property
    def ws_url(self):
        return f"ws://{self.backend_domain}:{self.ws_port}"

# Create a singleton config
config = Config()