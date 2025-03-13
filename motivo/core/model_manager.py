import torch
import logging
from pathlib import Path
from metamotivo.fb_cpr.huggingface import FBcprModel

from core.config import config
from utils.buffer_utils import download_buffer
from environment.env_setup import setup_environment

logger = logging.getLogger('model')

async def initialize_model_and_env():
    """Initialize model, environment and buffer data"""
    # Select device for computation
    if torch.cuda.is_available():
        device = "cuda"
        torch.backends.cudnn.benchmark = True
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    logger.info(f"Using device: {device}")
    
    # Load model
    logger.info("Loading model...")
    model = get_cached_model(config.default_model)
    model.to(device)
    model.eval()
    
    # Set up environment
    logger.info("Setting up environment...")
    env = setup_environment(device)
    
    # Download motion buffer
    logger.info("Downloading motion buffer...")
    buffer_data = download_buffer(model_name=config.default_model)
    
    return model, env, buffer_data

def get_cached_model(model_name: str, cache_dir: str = None) -> FBcprModel:
    """
    Get model from cache if it exists, otherwise download and cache it.
    
    Args:
        model_name: Name of the model to load
        cache_dir: Directory to store cached models
        
    Returns:
        Loaded model instance
    """
    # Use config cache dir if not specified
    if cache_dir is None:
        cache_dir = config.cache_dir
        
    # Create cache directory if it doesn't exist
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    # Create model-specific cache path
    model_cache_path = cache_path / model_name
    
    if model_cache_path.exists():
        logger.info(f"Loading model from cache: {model_cache_path}")
        model = FBcprModel.from_pretrained(str(model_cache_path))
    else:
        logger.info(f"Downloading model {model_name} and caching to: {model_cache_path}")
        model = FBcprModel.from_pretrained(f"facebook/{model_name}")
        model.save_pretrained(str(model_cache_path))
    
    return model