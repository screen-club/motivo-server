import os
import json
from pathlib import Path

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
        
        # Base paths
        self.storage_dir = 'storage'
        
        # Derived paths
        self.cache_dir = os.path.join(self.storage_dir, 'model')
        self.public_dir = os.path.join(os.path.dirname(os.getcwd()), 'public')
        self.shared_frames_dir = os.path.join(  self.public_dir, 'public', 'shared_frames')
        self.gemini_frame_path = os.path.join(self.shared_frames_dir, 'latest_frame.jpg')
        self.captured_frames_dir = os.path.join(self.storage_dir, 'captured_frames')
        self.downloads_dir = os.path.join(self.public_dir, 'downloads')
        
        # Create all necessary directories
        os.makedirs(self.shared_frames_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.captured_frames_dir, exist_ok=True)
        os.makedirs(self.downloads_dir, exist_ok=True)
        
        # Runtime config
        self.debug = os.getenv("MOTIVO_DEBUG", "0") == "1"
        self.in_container = os.path.exists('/.dockerenv') or os.environ.get('ENVIRONMENT') == 'production'
        
        # Set target FPS - use environment variable if provided, otherwise default to 30
        # Using 30 FPS as default for better stability - system appears to struggle with 60 FPS
        self.fps = int(os.getenv("MOTIVO_FPS", "30"))
        
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