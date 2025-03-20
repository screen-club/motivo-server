import os
import uuid
import time
import json
import logging
import threading
import traceback
import asyncio
import websockets
from datetime import datetime

# Flask and extensions
from flask import Flask, send_from_directory, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Authentication and file handling
from werkzeug.utils import secure_filename
from anthropic import Anthropic

# Local imports
from webserver.core.config import config
from webserver.services.gemini import GeminiService
from webserver.database.models import initialize_database, Content
from webserver.api.streaming import stream_bp

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('server')

# Record server start time
SERVER_START_TIME = time.time()

class WebServer:
    """Main web server application"""
    
    def __init__(self):
        # Create and configure Flask app
        self.app = Flask(__name__, static_folder=config.public_dir)
        CORS(self.app)
        
        # Initialize Socket.IO with improved configuration
        self.socketio = SocketIO(
            self.app,
            cors_allowed_origins="*",
            async_mode="threading",
            logger=False,  # Disable Socket.IO logging
            engineio_logger=False,  # Disable Engine.IO logging
            ping_timeout=30,
            ping_interval=25,
            max_http_buffer_size=5 * 1024 * 1024
        )
        
        # Initialize database
        initialize_database()
        
        # Initialize services
        self.anthropic_client = Anthropic(api_key=config.anthropic_api_key)
        self.gemini_service = GeminiService(api_key=config.google_api_key, port=config.api_port)
        
        # Register blueprints
        self.app.register_blueprint(stream_bp, url_prefix='/')
        
        # Register routes
        self._register_routes()
        
        # Register Socket.IO event handlers
        self._register_socketio_handlers()
        
        logger.info("Web server initialized")
    
    def _register_routes(self):
        """Register HTTP routes"""
        # Root and static files
        @self.app.route('/')
        def serve_index():
            return send_from_directory(config.public_dir, 'index.html')
        
        @self.app.route('/<path:path>')
        def serve_static(path):
            return send_from_directory(config.public_dir, path)
            
        # CORS preflight support for both /amjpeg and /api/amjpeg
        @self.app.route('/amjpeg', methods=['OPTIONS'])
        @self.app.route('/api/amjpeg', methods=['OPTIONS'])
        @self.app.route('/api/amjpeg/', methods=['OPTIONS'])
        def handle_mjpeg_options():
            """Handle CORS preflight requests for the MJPEG endpoint"""
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'  # 24 hours
            }
            return '', 204, headers
            
        # Test route to always return a blank image
        @self.app.route('/test_image', methods=['GET', 'HEAD'])
        def test_image():
            """Test route that always returns a simple image"""
            if request.method == 'HEAD':
                headers = {
                    'Content-Type': 'image/jpeg',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
                    'Cache-Control': 'no-cache, no-store, must-revalidate'
                }
                return '', 200, headers
            else:
                # Generate a tiny blank JPEG on the fly
                import io
                from PIL import Image
                
                # Create a simple 100x100 color image
                img = Image.new('RGB', (100, 100), color='blue')
                img_io = io.BytesIO()
                img.save(img_io, 'JPEG')
                img_io.seek(0)
                
                # Return the binary data with headers
                return send_file(
                    img_io,
                    mimetype='image/jpeg',
                    as_attachment=False
                )
                

            
        # Removed the problematic MJPEG stream route. 
        # We'll use static images from the public directory instead.
        
        # Health check
        @self.app.route('/health')
        def health_check():
            uptime = time.time() - SERVER_START_TIME
            return jsonify({
                "status": "ok",
                "uptime": uptime,
                "version": "1.0.0"
            })
            
        # API configuration
        @self.app.route('/api/server_conf')
        def get_api_conf():
            """Return API configuration information"""
            gemini_connected = self.gemini_service.is_connected() if hasattr(self.gemini_service, 'is_connected') else False
            
            return jsonify({
                "apis": {
                    "gemini": {
                        "connected": gemini_connected,
                        "status": self.gemini_service.connection_state if hasattr(self.gemini_service, 'connection_state') else "unknown"
                    },
                    "claude": {
                        "connected": bool(config.anthropic_api_key),
                        "status": "available" if config.anthropic_api_key else "no_api_key"
                    }
                },
                "server": {
                    "version": "1.0.0",
                    "uptime": time.time() - SERVER_START_TIME
                },
                "env": {
                    "backend_domain": config.api_host,
                    "ports": {
                        "api": config.api_port,
                        "websocket": config.api_port,  # Using the same port for both
                        "vibe": config.vibe_port
                    }
                }
            })
            
        # Gemini status check endpoint - explicitly for socket.io connectivity testing
        @self.app.route('/api/gemini_status')
        def get_gemini_status():
            """Return detailed Gemini API connection status"""
            gemini_connected = self.gemini_service.is_connected() if hasattr(self.gemini_service, 'is_connected') else False
            
            # Get more detailed status
            status = {
                "connected": gemini_connected,
                "connection_state": self.gemini_service.connection_state if hasattr(self.gemini_service, 'connection_state') else "unknown",
                "connection_attempts": self.gemini_service.connection_attempts if hasattr(self.gemini_service, 'connection_attempts') else 0,
                "last_connection_attempt": self.gemini_service.last_connection_attempt if hasattr(self.gemini_service, 'last_connection_attempt') else 0,
                "api_key_set": bool(config.google_api_key),
                "server_uptime": time.time() - SERVER_START_TIME,
                "timestamp": time.time()
            }
            
            # Return with CORS headers
            response = jsonify(status)
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response
        
        # File uploads
        @self.app.route('/upload', methods=['POST'])
        def upload_file():
            if 'file' not in request.files:
                return jsonify({"error": "No file part"}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({"error": "No selected file"}), 400
            
            # Save the file with a secure filename
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(config.uploads_dir, unique_filename)
            file.save(file_path)
            
            return jsonify({
                "success": True,
                "filename": unique_filename,
                "url": f"/uploads/{unique_filename}"
            })
        
        # Serve uploaded files
        @self.app.route('/uploads/<path:filename>')
        def serve_upload(filename):
            return send_from_directory(config.uploads_dir, filename)
            
        # Serve shared frames
        @self.app.route('/shared_frames/<path:filename>')
        def serve_shared_frame(filename):
            return send_from_directory(config.shared_frames_dir, filename)
            
      
        
        # Content management endpoints
        @self.app.route('/api/content', methods=['GET'])
        def get_all_content():
            content = Content.get_all()
            return jsonify(content)
        
        @self.app.route('/api/content', methods=['POST'])
        def add_content():
            data = request.json
            required_fields = ['title', 'thumbnail', 'type', 'data']
            
            # Validate required fields
            for field in required_fields:
                if field not in data:
                    return jsonify({"error": f"Missing required field: {field}"}), 400
            
            # Add content to database
            try:
                content_id = Content.add(
                    title=data['title'],
                    thumbnail=data['thumbnail'],
                    type=data['type'],
                    data=data['data'],
                    cache_file_path=data.get('cache_file_path'),
                    tags=data.get('tags', []),
                    users=data.get('users', [])
                )
                return jsonify({"success": True, "id": content_id})
            except Exception as e:
                logger.error(f"Error adding content: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/content/<int:content_id>', methods=['DELETE'])
        def delete_content(content_id):
            try:
                Content.delete_item(content_id)
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Error deleting content: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/content/<int:content_id>', methods=['PUT'])
        def update_content(content_id):
            data = request.json
            try:
                Content.update_content(content_id, **data)
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Error updating content: {str(e)}")
                return jsonify({"error": str(e)}), 500
                
        # Modern presets API endpoints
        @self.app.route('/api/presets', methods=['GET'])
        def get_all_presets():
            """Return all presets from the database"""
            try:
                presets = Content.get_all()
                return jsonify(presets)
            except Exception as e:
                logger.error(f"Error fetching presets: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/presets', methods=['POST'])
        def add_preset():
            """Add a new preset to the database"""
            data = request.json
            required_fields = ['title', 'thumbnail', 'type', 'data']
            
            # Validate required fields
            for field in required_fields:
                if field not in data:
                    return jsonify({"error": f"Missing required field: {field}"}), 400
            
            # Add preset to database
            try:
                preset_id = Content.add(
                    title=data['title'],
                    thumbnail=data['thumbnail'],
                    type=data['type'],
                    data=data['data'],
                    cache_file_path=data.get('cache_file_path'),
                    tags=data.get('tags', []),
                    users=data.get('users', [])
                )
                return jsonify({"id": preset_id}), 201
            except Exception as e:
                logger.error(f"Error adding preset: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/presets/<int:preset_id>', methods=['DELETE'])
        def delete_preset(preset_id):
            """Delete a preset from the database"""
            try:
                Content.delete_item(preset_id)
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Error deleting preset: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/presets/<int:preset_id>', methods=['PUT'])
        def update_preset(preset_id):
            """Update an existing preset"""
            data = request.json
            try:
                Content.update_content(preset_id, **data)
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Error updating preset: {str(e)}")
                return jsonify({"error": str(e)}), 500
                
        # Legacy conf API endpoints - maintained for backward compatibility
        @self.app.route('/api/conf', methods=['GET'])
        def get_all_configs():
            """Return all configurations from the database"""
            try:
                configs = Content.get_all()
                return jsonify(configs)
            except Exception as e:
                logger.error(f"Error fetching configs: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/conf', methods=['POST'])
        def add_config():
            """Add a new configuration to the database"""
            data = request.json
            required_fields = ['title', 'thumbnail', 'type', 'data']
            
            # Validate required fields
            for field in required_fields:
                if field not in data:
                    return jsonify({"error": f"Missing required field: {field}"}), 400
            
            # Add config to database
            try:
                config_id = Content.add(
                    title=data['title'],
                    thumbnail=data['thumbnail'],
                    type=data['type'],
                    data=data['data'],
                    cache_file_path=data.get('cache_file_path'),
                    tags=data.get('tags', []),
                    users=data.get('users', [])
                )
                return jsonify({"id": config_id}), 201
            except Exception as e:
                logger.error(f"Error adding config: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/conf/<int:config_id>', methods=['DELETE'])
        def delete_config(config_id):
            """Delete a configuration from the database"""
            try:
                Content.delete_item(config_id)
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Error deleting config: {str(e)}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/conf/<int:config_id>', methods=['PUT'])
        def update_config(config_id):
            """Update an existing configuration"""
            data = request.json
            try:
                Content.update_content(config_id, **data)
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Error updating config: {str(e)}")
                return jsonify({"error": str(e)}), 500
    
    def _register_socketio_handlers(self):
        """Register Socket.IO event handlers"""
        @self.socketio.on('connect')
        def handle_connect():
            emit('connection_status', {"status": "connected"})
            
        @self.socketio.on('gemini_connect')
        def handle_gemini_connect():
            """Handle Gemini connection check request"""
            try:
                gemini_connected = self.gemini_service.is_connected()
                connection_state = self.gemini_service.connection_state if hasattr(self.gemini_service, 'connection_state') else "unknown"
                
                # Send Gemini connection status to the client
                emit('gemini_connection_status', {
                    'connected': gemini_connected,
                    'state': connection_state,
                    'timestamp': time.time(),
                    'client_id': request.sid,
                    'socketio_connected': True  # Indicator that Socket.IO itself is working
                })
            except Exception as e:
                logger.error(f"Error in gemini_connect handler: {str(e)}")
                emit('gemini_connection_status', {
                    'connected': False,
                    'state': "error",
                    'error_message': str(e),
                    'timestamp': time.time(),
                    'client_id': request.sid,
                    'socketio_connected': True
                })
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            pass
        
        @self.socketio.on('claude_message')
        def handle_claude_message(data):
            try:
                # Call Claude API
                response = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=4000,
                    messages=[
                        {"role": "user", "content": data.get('message', '')}
                    ]
                )
                
                # Return Claude's response
                emit('claude_response', {
                    "message": response.content[0].text,
                    "id": data.get('id')
                })
            except Exception as e:
                logger.error(f"Error processing Claude message: {str(e)}")
                emit('claude_error', {"error": str(e), "id": data.get('id')})
        
        @self.socketio.on('gemini_message')
        def handle_gemini_message(data):
            try:
                # Get the message from either 'message' or 'text' field for compatibility
                message_text = data.get('message', data.get('text', ''))
                
                # Always include the image with text messages by default
                include_image = data.get('include_image', True)
                add_to_existing = data.get('add_to_existing', False)
                
                # Check if a frame_url was provided directly from the client
                frame_url = data.get('frame_url')
                
                # Log the received frame_url for debugging
                if frame_url:
                    logger.info(f"Received frame_url in gemini_message: {frame_url}")
                
                # Get or generate message_id - this is critical for matching responses
                message_id = data.get('id')
                if not message_id:
                    message_id = str(uuid.uuid4())
                    logger.info(f"Generated new message ID: {message_id}")
                else:
                    logger.info(f"Using provided message ID: {message_id}")
                
                try:
                    if include_image:
                        # Image inclusion requested, validate and prepare frame URL
                        
                        if not frame_url:

                            error_msg = "No frame URL provided and no alternative sources available"
                            logger.error(error_msg)
                            raise ValueError(error_msg)
                        
                        # Convert URL path to absolute file path
                        if frame_url.startswith('/'):
                            # Remove the leading slash for path joining
                            relative_path = frame_url[1:]
                            # Construct full path by joining with the public directory
                            full_path = os.path.join(self.app.static_folder, relative_path)
                            logger.info(f"Converted URL {frame_url} to file path: {full_path}")
                        else:
                            # If not starting with /, assume it's already formatted correctly
                            full_path = os.path.join(self.app.static_folder, frame_url)
                        
                        # Check if the file actually exists
                        if not os.path.exists(full_path):
                            error_msg = f"Image file not found at {full_path}"
                            logger.error(error_msg)
                            raise FileNotFoundError(error_msg)
                        
                        # Create a capture info object with the URL and full path
                        capture_info = {
                            "path": frame_url,
                            "timestamp": int(time.time()),
                            "timestamp_str": time.strftime('%d/%m/%Y %H:%M:%S'),
                            "fullpath": full_path
                        }
                        
                        logger.info(f"Using frame URL: {frame_url}")
                        
                        # Queue the message with the validated capture info
                        message_id = self.gemini_service.queue_message(
                            message_text,
                            message_id,  # Pass the message_id explicitly
                            request.sid,
                            include_image=True,
                            capture_info=capture_info,
                            add_to_existing=add_to_existing
                        )
                        
                        # Log that we've queued the message with this capture info
                        logger.info(f"Queued Gemini message with image path: {capture_info.get('path')} and message ID: {message_id}")
                    else:
                        # No image inclusion requested, just send the text message
                        message_id = self.gemini_service.queue_message(
                            message_text,
                            message_id,  # Pass the message_id explicitly
                            request.sid,
                            include_image=False,
                            add_to_existing=add_to_existing
                        )
                
                except (ValueError, FileNotFoundError) as e:
                    logger.error(f"Error preparing image for Gemini: {str(e)}")
                    emit('gemini_error', {
                        "error": str(e), 
                        "id": data.get('id'),
                        "type": "image_error"
                    })
                    return
                
                # Process any pending responses from Gemini
                def handle_gemini_response(message):
                    try:
                        if message["type"] == "gemini_response":
                            # Send the response back to the client
                            content = message.get("content", "")
                            complete = message.get("complete", False)
                            
                            # Create response with standard fields
                            response_data = {
                                "message": content,
                                "content": content,
                                "complete": complete,
                                "id": data.get('id')  # This data['id'] may be the wrong reference
                            }
                            
                            # Use the message_id from the Gemini message for consistency
                            if message.get("message_id"):
                                response_data["id"] = message.get("message_id")
                            
                            # Include image information if present in the message
                            if "image_path" in message:
                                # Make sure to use the same field names the frontend expects
                                response_data["image_path"] = message["image_path"]
                                response_data["image_timestamp"] = message.get("image_timestamp", time.time())
                                response_data["timestamp_str"] = message.get("timestamp_str", time.strftime('%d/%m/%Y %H:%M:%S'))
                            
                            # Add message ID to response for frontend tracking
                            response_data["message_id"] = message.get("message_id", "unknown")
                            
                            # Emit the response with all information
                            emit('gemini_response', response_data)
                    except Exception as e:
                        logger.error(f"Error handling Gemini response: {str(e)}")
                
                # Process any pending responses
                self.gemini_service.process_incoming_messages(handle_gemini_response)
                
            except Exception as e:
                logger.error(f"Error queueing Gemini message: {str(e)}")
                emit('gemini_error', {"error": str(e), "id": data.get('id')})
                

  
        # Periodically process incoming messages from Gemini
        def process_gemini_messages():
            while True:
                try:
                    # Process any pending responses from Gemini
                    def handle_response(message):
                        try:
                            if message["type"] == "gemini_response":
                                # Get the client ID from the message
                                client_id = message.get("client_id", "system")
                                content = message.get("content", "")
                                complete = message.get("complete", False)
                                
                                # Prepare response data with all fields from the original message
                                response_data = {
                                    "message": content,
                                    "content": content,
                                    "complete": complete,
                                    "id": message.get("id", None)
                                }
                                
                                # Important: Include image data if available
                                if "image_path" in message:
                                    response_data["image_path"] = message["image_path"]
                                    response_data["image_timestamp"] = message.get("image_timestamp", time.time())
                                    
                                    # Include human-readable timestamp if available
                                    if "timestamp_str" in message:
                                        response_data["timestamp_str"] = message["timestamp_str"]
                                    else:
                                        response_data["timestamp_str"] = time.strftime('%d/%m/%Y %H:%M:%S')
                                    
                                    # Add message ID to response for frontend tracking
                                    response_data["message_id"] = message.get("message_id", "unknown")
                                
                                # Emit the complete response to all clients
                                self.socketio.emit('gemini_response', response_data)
                        except Exception as e:
                            logger.error(f"Error handling response in background thread: {str(e)}")
                    
                    # Process any pending responses
                    self.gemini_service.process_incoming_messages(handle_response)
                    
                    # Wait a bit before checking again
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error in Gemini message processor: {str(e)}")
                    time.sleep(1)
        
        # Start the message processor in a background thread
        message_processor_thread = threading.Thread(target=process_gemini_messages)
        message_processor_thread.daemon = True
        message_processor_thread.start()
    
    def start(self):
        """Start the web server"""
        # Start Gemini service
        self.gemini_service.start()
        
        # Check if we're on macOS or a local environment
        import platform
        is_mac = platform.system() == 'Darwin'
        is_local = config.api_host in ['localhost', '127.0.0.1', '0.0.0.0'] or is_mac
        
        # Set debug mode for local/mac development
        debug_mode = is_local
        
        # Start Socket.IO server
        logger.info(f"Starting web server on port {config.api_port}...")
        self.socketio.run(self.app, host='0.0.0.0', port=config.api_port, debug=debug_mode)

# Create singleton server instance
server = WebServer()