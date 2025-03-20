import logging
import sys

def setup_logging(debug=False):
    """Configure logging for the application"""
    level = logging.DEBUG if debug else logging.INFO
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console)
    
    # Create specific loggers
    create_logger('network', level)
    create_logger('model', level)
    create_logger('webrtc', level)
    create_logger('rewards', level)
    
    # Set higher log levels for noisy third-party libraries
    logging.getLogger('aioice.ice').setLevel(logging.WARNING)  # Suppress ICE candidate logs
    logging.getLogger('aioice').setLevel(logging.WARNING)
    logging.getLogger('aiortc').setLevel(logging.WARNING)
    
    return logger

def create_logger(name, level):
    """Create a named logger with the specified level"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger