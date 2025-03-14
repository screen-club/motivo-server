import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO,
                  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('config')

class Config:
    """Centralized configuration management"""
    
    def __init__(self):
        # Base paths
        self.base_dir = str(Path(__file__).resolve().parents[3])
        
        # Check if we're in a nested path or not
        if os.path.exists(os.path.join(self.base_dir, 'motivo-server')):
            # We're in liminal/motivo-server
            self.motivo_server_dir = os.path.join(self.base_dir, 'motivo-server')
        else:
            # We're already in motivo-server directory
            self.motivo_server_dir = self.base_dir
        
        self.public_dir = os.path.join(self.motivo_server_dir, 'public')
        
        # Create the public dir if needed
        os.makedirs(self.public_dir, exist_ok=True)
        
        self.storage_dir = os.path.join(self.motivo_server_dir, 'storage')
        
        # Storage paths
        self.db_dir = os.path.join(self.storage_dir, 'db')
        self.uploads_dir = os.path.join(self.storage_dir, 'uploads')
        self.streams_dir = os.path.join(self.storage_dir, 'streams')
        self.shared_frames_dir = os.path.join(self.storage_dir, 'shared_frames')
        
        # URLs and ports
        self.api_host = os.getenv('VITE_API_URL', 'localhost')
        self.api_port = int(os.getenv('VITE_API_PORT', 5002))
        self.vibe_port = int(os.getenv('VITE_VIBE_PORT', 5000))
        
        # API keys
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY', '')
        self.google_api_key = os.getenv('GOOGLE_API_KEY', '')
        
        # System files
        self.webserver_dir = os.path.dirname(os.path.dirname(__file__))
        self.system_instructions_path = os.path.join(self.webserver_dir, 'system_instructions.txt')
        
        # Create necessary directories
        self._create_directories()
        
        # Validate configuration
        self._validate_config()
        
        logger.info("Configuration initialized")
    
    def _create_directories(self):
        """Create necessary directories"""
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.db_dir, exist_ok=True)
        os.makedirs(self.uploads_dir, exist_ok=True)
        os.makedirs(self.streams_dir, exist_ok=True)
        os.makedirs(self.shared_frames_dir, exist_ok=True)
    
    def _validate_config(self):
        """Validate configuration settings"""
        if not self.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY environment variable is not set")
        
        if not self.google_api_key:
            logger.warning("GOOGLE_API_KEY environment variable is not set")
        
        if not os.path.exists(self.system_instructions_path):
            logger.warning(f"System instructions file not found at {self.system_instructions_path}")
    
    @property
    def api_url(self):
        """Get the API URL"""
        return f"http://{self.api_host}:{self.api_port}"
    


# Create a singleton configuration
config = Config()