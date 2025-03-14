#!/usr/bin/env python3
"""
Main entry point for the webserver.
"""
import os
import sys
import logging

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webserver.core.server import server

# Configure logging with reduced verbosity
logging.basicConfig(
    level=logging.WARNING,  # Set default level to WARNING to reduce verbosity
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Only keep INFO level for critical components
logger = logging.getLogger('main')
logger.setLevel(logging.INFO)

# Set specific loggers to WARNING or higher
logging.getLogger('engineio.server').setLevel(logging.WARNING)
logging.getLogger('socketio.server').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

def main():
    """Main function"""
    try:
        # Start the server
        logger.info("Starting Motivo webserver...")
        server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down due to keyboard interrupt")
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}", exc_info=True)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())