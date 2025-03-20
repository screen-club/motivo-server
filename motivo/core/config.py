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
        self.public_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..', 'public'))
        self.storage_dir = os.path.join(self.public_dir, 'storage')
        
        # Derived paths
        self.cache_dir = os.path.join(self.storage_dir, 'cache')
        self.shared_frames_dir = os.path.join(self.storage_dir, 'shared_frames')
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
        self.fps = 60
        
        # Default reward configuration
        self.default_reward_config = {
            'rewards': [
                { 'name': 'move-ego', 'move_speed': 0.0, 'stand_height': 1.4 }
            ],
            'weights': [1.0]
        }
        
        # Video settings
        self.default_video_quality = "medium"
        self.video_qualities = ["low", "medium", "high", "hd"]
        
    @property
    def ws_url(self):
        return f"ws://{self.backend_domain}:{self.ws_port}"

# Create a singleton config
config = Config()