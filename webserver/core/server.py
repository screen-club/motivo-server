import os
import uuid
import time
import json
import logging
import threading
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
        
        # Initialize Socket.IO
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode="threading")
        
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
                
        # Debug route to check file existence
        @self.app.route('/debug_frame')
        def debug_frame():
            """Debug endpoint to check frame file"""
            frame_path = os.path.join(config.shared_frames_dir, 'latest_frame.jpg')
            
            file_info = {
                "path": frame_path,
                "exists": os.path.exists(frame_path),
                "is_file": os.path.isfile(frame_path) if os.path.exists(frame_path) else False,
                "size_bytes": os.path.getsize(frame_path) if os.path.exists(frame_path) else 0,
                "permissions": oct(os.stat(frame_path).st_mode & 0o777) if os.path.exists(frame_path) else "N/A",
                "shared_frames_dir": config.shared_frames_dir,
                "shared_dir_exists": os.path.exists(config.shared_frames_dir),
                "full_path": os.path.abspath(frame_path)
            }
            
            return jsonify(file_info)
            
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
        @self.app.route('/api/conf')
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
        
        # Content management
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
                    tags=data.get('tags', [])
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
    
    def _register_socketio_handlers(self):
        """Register Socket.IO event handlers"""
        @self.socketio.on('connect')
        def handle_connect():
            logger.info(f"Client connected: {request.sid}")
            emit('connection_status', {"status": "connected"})
            
        @self.socketio.on('gemini_connect')
        def handle_gemini_connect():
            """Handle Gemini connection check request"""
            logger.info(f"Gemini connection check requested by client: {request.sid}")
            gemini_connected = self.gemini_service.is_connected()
            
            # Send Gemini connection status to the client
            emit('gemini_connection_status', {
                'connected': gemini_connected,
                'state': self.gemini_service.connection_state if hasattr(self.gemini_service, 'connection_state') else "unknown",
                'timestamp': time.time()
            })
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            logger.info(f"Client disconnected: {request.sid}")
        
        @self.socketio.on('claude_message')
        def handle_claude_message(data):
            try:
                # Process Claude message
                logger.info(f"Received Claude message: {data.get('message', '')[:50]}...")
                
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
                
                # Queue message for Gemini service
                message_id = self.gemini_service.queue_message(
                    message_text,
                    data.get('id'),
                    request.sid
                )
                
                # Process any pending responses from Gemini
                def handle_gemini_response(message):
                    try:
                        if message["type"] == "gemini_response":
                            # Send the response back to the client
                            content = message.get("content", "")
                            complete = message.get("complete", False)
                            
                            # Emit the response with both content and message fields for compatibility
                            # with different frontend implementations
                            emit('gemini_response', {
                                "message": content,
                                "content": content,
                                "complete": complete,
                                "id": data.get('id')
                            })
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
                                
                                # Emit the response to all clients with both content and message fields
                                self.socketio.emit('gemini_response', {
                                    "message": content,
                                    "content": content,
                                    "complete": complete,
                                    "id": message.get("id", None)
                                })
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
        
        # Start Socket.IO server
        logger.info(f"Starting web server on port {config.api_port}...")
        self.socketio.run(self.app, host='0.0.0.0', port=config.api_port)

# Create singleton server instance
server = WebServer()