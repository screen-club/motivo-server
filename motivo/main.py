import asyncio
import websockets
import logging
import torch
from asyncio.exceptions import CancelledError
import traceback

from core.config import config
from core.state import app_state
from core.model_manager import initialize_model_and_env
from core.simulation import run_simulation_loop
from core.logging_config import setup_logging
from network.websocket_handlers import handle_websocket

# Set up exception handler for asyncio
def global_exception_handler(loop, context):
    """Global exception handler for asyncio errors"""
    exception = context.get('exception')
    message = context.get('message')
    logger = logging.getLogger()

    logger.error(f"Exception from global_exception_handler: {exception}")

    if exception and isinstance(exception, AttributeError) and "'NoneType' object has no attribute" in str(exception):
        logger.info(f"Suppressed NoneType attribute error: {str(exception)}")
        return
    
    if message and "'NoneType' object has no attribute" in message:
        logger.info(f"Suppressed NoneType attribute error from message: {message}")
        return
        
    loop.default_exception_handler(context)

async def initialize_default_context():
    """Initialize the default context for the motion model"""
    default_config = config.default_reward_config
    
    # Try to get from cache first
    cache_key = app_state.context_cache.get_cache_key(default_config)
    cached_z, _ = app_state.context_cache._get_cached_context_impl(cache_key)

    if cached_z is not None:
        logging.info("Using cached default context")
        app_state.message_handler.set_default_z(cached_z)
        return
            
    logging.info("Default context not found in cache, computing synchronously...")
    
    # Compute default context directly and synchronously to ensure we have it at startup
    try:
        # Use direct computation for default context instead of get_reward_context
        # because we need this to complete before continuing
        from rewards.reward_context import compute_reward_context
        default_z = compute_reward_context(
            default_config,
            app_state.env,
            app_state.model,
            app_state.buffer_data
        )
        
        if default_z is None:
            logging.error("Failed to compute default context, will use zeros")
            # Create a default tensor 
            latent_dim = 256  # Common latent dimension for these models
            default_z = torch.zeros((1, latent_dim), device=app_state.model.cfg.device)
            
        # Save the context to cache
        logging.info("Saving default context to cache")
        app_state.context_cache._save_to_disk(cache_key, default_z)
        
        # Add to memory cache
        if len(app_state.context_cache.computation_cache) < app_state.context_cache.max_memory_entries:
            app_state.context_cache.computation_cache[cache_key] = default_z
            
        # Set as default
        app_state.message_handler.set_default_z(default_z)
        
    except Exception as e:
        logging.error(f"Error computing default context: {str(e)}")
        # Create an emergency fallback tensor 
        latent_dim = 256  # Common latent dimension for these models
        default_z = torch.zeros((1, latent_dim), device=app_state.model.cfg.device)
        app_state.message_handler.set_default_z(default_z)
        logging.warning("Using zeros tensor as default context due to computation error")

async def main():
    """Main application entry point"""
    try:
        # Set up logging
        logger = setup_logging(debug=config.debug)
        logger.info("Starting Motivo Server")
        
        # Set asyncio exception handler
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(global_exception_handler)
        
        # Initialize model, environment and buffer
        model, env, buffer_data = await initialize_model_and_env()
        
        # Initialize app state with model components
        app_state.initialize(model, env, buffer_data)
        
        # Set up default context
        await initialize_default_context()
        
        # Start WebSocket server
        logger.info(f"Starting WebSocket server on port {config.ws_port}...")
        server = await websockets.serve(
            handle_websocket, 
            "0.0.0.0", 
            config.ws_port
        )
        logger.info(f"WebSocket server started at {config.ws_url}")
        
        # Run simulation and server together
        await asyncio.gather(
            server.wait_closed(),
            run_simulation_loop()
        )
        
    except KeyboardInterrupt:
        logger.info("Shutting down due to keyboard interrupt...")
    except CancelledError:
        logger.info("Tasks cancelled, shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
    finally:
        # Clean up resources
        await app_state.cleanup()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())