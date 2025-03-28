import torch
import logging
from concurrent.futures import ThreadPoolExecutor

from core.config import config
from utils.cache_utils import RewardContextCache
from utils.display_utils import DisplayManager
from network.ws_manager import WebSocketManager
from network.webrtc_manager import WebRTCManager

# We import MessageHandler later to avoid circular imports
# from handlers.message_handler import MessageHandler

logger = logging.getLogger('state')

class AppState:
    """
    Central application state manager that holds all shared components
    and provides interaction between them.
    """
    
    def __init__(self):
        # Core components (initialized later)
        self.model = None
        self.env = None
        self.buffer_data = None
        
        # Support services
        self.thread_pool = ThreadPoolExecutor(max_workers=1)
        self.ws_manager = WebSocketManager()
        self.webrtc_manager = WebRTCManager(video_quality=config.default_video_quality)
        self.display_manager = DisplayManager(headless=config.in_container)
        
        # Will initialize after model/env are loaded
        self.context_cache = None
        self.message_handler = None
        
        # Flags
        self.is_initialized = False
        self.is_running = False
    
    def initialize(self, model, env, buffer_data):
        """Initialize with model, environment and buffer data"""
        from handlers.message_handler import MessageHandler
        
        self.model = model
        self.env = env
        self.buffer_data = buffer_data
        
        # Create cache with all required components
        self.context_cache = RewardContextCache(
            model=model, 
            env=env, 
            buffer_data=buffer_data
        )
        
        # Initialize message handler
        self.message_handler = MessageHandler(
            model, 
            env, 
            self.ws_manager, 
            self.context_cache
        )
        self.message_handler.set_buffer_data(buffer_data)
        
        # Set environment in WebRTC manager
        self.webrtc_manager.set_environment(env)
        
        self.is_initialized = True
        logger.info("Application state initialized")
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources...")
        self.is_running = False
        
        # Close all WebRTC connections
        if self.webrtc_manager:
            await self.webrtc_manager.close_all_connections()
            
        # Clean up display
        if self.display_manager:
            self.display_manager.cleanup()
            
        # Shut down thread pool
        if self.thread_pool:
            self.thread_pool.shutdown()
        
        logger.info("Cleanup complete")

# Create singleton app state
app_state = AppState()