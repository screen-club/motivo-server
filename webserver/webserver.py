# ============================================================================
# IMPORTS
# ============================================================================
# Standard library imports
import os
import uuid
import traceback
from datetime import datetime
import subprocess
import ffmpeg
import time
import re
import json
import threading
import logging

# Third-party imports
from flask import Flask, send_from_directory, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from anthropic import Anthropic
from dotenv import load_dotenv
import requests


# Try imports as package first, then as local modules if that fails
try:
    from webserver.services.gemini import GeminiService
    from webserver.database.models import Content, initialize_database
except ImportError:
   
    # Try local imports
    from services.gemini import GeminiService
    from database.models import Content, initialize_database


# ============================================================================
# CONFIGURATION
# ============================================================================
# Load environment variables
load_dotenv()


# Environment variables
VITE_API_URL = os.getenv('VITE_API_URL') or 'localhost'
VITE_API_PORT = os.getenv('VITE_API_PORT') or 5002
VITE_VIBE_URL = os.getenv('VITE_VIBE_URL') or 5000
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY' or "")
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY' or "")

if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY environment variable is not set. Some functionality will be limited.")

if not GOOGLE_API_KEY:
    print("WARNING: GOOGLE_API_KEY environment variable is not set. Gemini functionality will be disabled.")

# Record server start time
SERVER_START_TIME = time.time()

# Define storage paths
STORAGE_BASE = 'storage/video'
RAW_VIDEO_FOLDER = f'{STORAGE_BASE}/raw'
TRIMMED_VIDEO_FOLDER = f'{STORAGE_BASE}/trimmed'
RENDERS_FOLDER = f'{STORAGE_BASE}/renders'

# Create necessary directories
for folder in [RAW_VIDEO_FOLDER, TRIMMED_VIDEO_FOLDER, RENDERS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Define the shared frames path
STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'storage'))
SHARED_FRAMES_DIR =  os.path.abspath(os.path.join(STORAGE_DIR, 'shared_frames'))
GEMINI_FRAME_PATH = os.path.join(SHARED_FRAMES_DIR, 'latest_frame.jpg')

ALLOWED_EXTENSIONS = {'mp4', 'webm', 'ogg'}
STATUS_LOG_INTERVAL = 10  # Only log status checks every 10 seconds

# ============================================================================
# INITIALIZATION
# ============================================================================
# Initialize Flask app
app = Flask(__name__)
app.config['RAW_VIDEO_FOLDER'] = RAW_VIDEO_FOLDER
app.config['TRIMMED_VIDEO_FOLDER'] = TRIMMED_VIDEO_FOLDER
app.config['RENDERS_FOLDER'] = RENDERS_FOLDER

# Configure CORS
CORS(app, resources={
    r"/*": {
        "origins": ["*"],
        "methods": ["GET", "POST", "DELETE", "PUT"],
        "allow_headers": ["Content-Type"]
    }
})

# Initialize Flask-SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
client_logger = logging.getLogger('client_connections')
client_logger.setLevel(logging.INFO)

# Initialize services
try:
    # Initialize database
    initialize_database()
    
    # Load system instructions
    try:
        with open('system_instructions.txt', 'r', encoding='utf-8') as f:
            SYSTEM_INSTRUCTIONS = f.read()
    except Exception as e:
        print(f"Warning: Could not load system instructions: {str(e)}")
        SYSTEM_INSTRUCTIONS = ""
    
    # Initialize Anthropic client (if API key is available)
    if ANTHROPIC_API_KEY:
        anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)
    else:
        anthropic = None
        print("Anthropic client initialization skipped due to missing API key")
    
    # Initialize Gemini service (if API key is available)
    if GOOGLE_API_KEY:
        gemini_service = GeminiService(port=5002, api_key=GOOGLE_API_KEY)
        gemini_service.start()
    else:
        gemini_service = None
        print("Gemini service initialization skipped due to missing API key")
    
except Exception as e:
    print(f"Initialization error: {str(e)}")
    traceback.print_exc()
    gemini_service = None
    anthropic = None

# Global state
chat_histories = {}
active_clients = {}
connection_requests_count = 0
last_status_log_time = 0

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_client_info():
    """Extract useful client information from request"""
    sid = request.sid
    ip = request.remote_addr or 'unknown'
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # Try to extract browser name
    browser = 'Unknown'
    if user_agent:
        # Simple browser detection
        browser_match = re.search(r'(Chrome|Safari|Firefox|Edge|Opera)[/\s]([0-9.]+)', user_agent)
        if browser_match:
            browser = browser_match.group(1)
    
    return {
        'sid': sid,
        'ip': ip,
        'browser': browser,
        'user_agent': user_agent,
        'connected_at': time.time()
    }

def get_active_client_count():
    """Get count of active clients, grouped by IP to represent real users"""
    if not active_clients:
        return 0
        
    # Count unique IPs
    unique_ips = set(client['ip'] for client in active_clients.values())
    return len(unique_ips)

def broadcast_gemini_response(response):
    """Broadcast Gemini response to all clients"""
    socketio.emit('gemini_response', response)

# ============================================================================
# BACKGROUND TASKS
# ============================================================================
def broadcast_initial_status():
    """Broadcast initial Gemini connection status after delay"""
    time.sleep(3)  # Give service time to connect
    connected = gemini_service.is_connected()
    socketio.emit('gemini_connection_status', {
        'connected': connected,
        'timestamp': time.time()
    })

def process_gemini_messages():
    """Process incoming messages from Gemini service"""
    # Create a local logging reference
    logger = logging.getLogger("webserver.gemini")
    
    while True:
        if gemini_service:
            def handle_message(message):
                try:
                    # Log the received message type for debugging
                    logger.info(f"Processing Gemini message : {message.get('type')}")
                    
                    content = message.get("content", "")
                    complete = message.get("complete", False)
                    
                    # Create response with standard fields
                    response_data = {
                        "message": content,
                        "content": content,
                        "complete": complete,
                        'timestamp': message.get('timestamp', time.time()),

                    }
                    
                    # Use the message_id from the Gemini message for consistency
                    if message.get("message_id"):
                        response_data["id"] = message.get("message_id")
                    
                    print("message", message)
                    if "image_path" in message:
                        # Make sure to use the same field names the frontend expects
                        print("image_path", message["image_path"])
                        response_data["image_path"] = message["image_path"]
                        response_data["image_timestamp"] = message.get("image_timestamp", time.time())
                        response_data["timestamp_str"] = message.get("timestamp_str", time.strftime('%d/%m/%Y %H:%M:%S'))
                    else:
                        print("No image path in message")
                    
                    # Add message ID to response for frontend tracking
                    response_data["message_id"] = message.get("message_id", "unknown")
                    
                    # Broadcast message to all connected clients
                    socketio.emit('gemini_response',response_data)
                    logger.info(f"Broadcasted message to clients: {message.get('type')}")
                except Exception as e:
                    logger.error(f"Error handling Gemini message: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            # Process any pending messages with proper error handling
            try:
                gemini_service.process_incoming_messages(handle_message)
            except Exception as e:
                logger.error(f"Error in Gemini message processing: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Small sleep to prevent high CPU usage
        time.sleep(0.1)

# Start background threads
if gemini_service:
    threading.Thread(target=broadcast_initial_status, daemon=True).start()

gemini_thread = threading.Thread(target=process_gemini_messages)
gemini_thread.daemon = True
gemini_thread.start()

# ============================================================================
# SOCKETIO EVENT HANDLERS
# ============================================================================
@socketio.on('connect')
def handle_connect():
    """Handle Socket.IO client connection"""
    client_info = get_client_info()
    client_id = client_info['sid']
    
    # Store client info
    active_clients[client_id] = client_info
    
    # Only log unique IPs to reduce noise
    ip_count = sum(1 for c in active_clients.values() if c['ip'] == client_info['ip'])
    if ip_count == 1:
        # First connection from this IP
        client_logger.info(f"[CLIENT] New client connected from {client_info['ip']} ({client_info['browser']})")
    else:
        # Reconnection from same IP - only log at debug level
        client_logger.debug(f"[CLIENT] Client reconnected from {client_info['ip']} ({client_info['browser']}) - {ip_count} connections from this IP")
    
    # Send initial connection status for Gemini
    if gemini_service:
        connected = gemini_service.is_connected()
        emit('gemini_connection_status', {
            'connected': connected,
            'timestamp': time.time()
        })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle Socket.IO client disconnection"""
    client_id = request.sid
    
    if client_id in active_clients:
        client_info = active_clients.pop(client_id)
        
        # Count remaining connections from this IP
        ip_count = sum(1 for c in active_clients.values() if c['ip'] == client_info['ip'])
        
        if ip_count == 0:
            # Last connection from this IP
            client_logger.info(f"[CLIENT] Client disconnected from {client_info['ip']} ({client_info['browser']})")
        else:
            # Still have other connections from this IP
            client_logger.debug(f"[CLIENT] Client session ended from {client_info['ip']} - {ip_count} remaining connections")

@socketio.on('gemini_connect')
def handle_gemini_connect():
    """Handle dedicated Gemini connection"""
    global connection_requests_count
    connection_requests_count += 1
    
    # Log periodically or on first request
    if connection_requests_count <= 1 or connection_requests_count % 10 == 0:
        client_id = request.sid
        client_info = active_clients.get(client_id, {'ip': 'unknown', 'browser': 'unknown'})
        client_logger.info(f"[CLIENT] Gemini connection request from {client_info['ip']} ({connection_requests_count} total requests)")
        gemini_service.ensure_connection()
    
    # Send current status immediately
    if gemini_service:
        connected = gemini_service.is_connected()
        emit('gemini_status', {
            'connected': connected,
            'timestamp': time.time()
        })

@socketio.on('gemini_message')
def handle_gemini_message(data):
    """Handle text message to Gemini with image support"""
    if not gemini_service:
        emit('gemini_error', {
            'message': 'Gemini service not available',
            'timestamp': time.time()
        })
        return

    
    try:
        # Extract all possible fields from data
        message_text = data.get('message', data.get('text', ''))
        message_id = data.get('id', str(uuid.uuid4()))
        include_image = data.get('include_image', True)
        add_to_existing = data.get('add_to_existing', False)
        frame_url = data.get('frame_url')
        auto_correct = data.get('auto_correct', False)
        
        # Get client info
        client_id = request.sid
        
        client_logger.info(f"Handling Gemini message: ID={message_id}, include_image={include_image}, frame_url={frame_url}")
        
        try:
            capture_info = None
            if include_image:
                if frame_url:
                    # Handle frame URL from storage/shared_frames
                    
                    
                    # Get file stats
                    print("frame_url", frame_url)
                    file_stats = os.stat(frame_url)

                    # Create comprehensive capture info
                    capture_info = {
                        "path": frame_url,
                        "fullpath": frame_url,
                        "filename": os.path.basename(frame_url),
                        "timestamp": int(time.time()),
                        "timestamp_str": time.strftime('%d/%m/%Y %H:%M:%S'),
                        "file_size": file_stats.st_size,
                        "last_modified": file_stats.st_mtime,
                        "created": file_stats.st_ctime,
                        "is_shared_frame": frame_url.startswith('/storage/shared_frames/'),
                        "client_id": client_id
                    }
                    
                    client_logger.info(f"Prepared capture info for {frame_url}: {capture_info}")
                else:
                    # No frame URL provided
                    client_logger.warning("Include image requested but no frame_url provided")
                    include_image = False

            # Queue the message
            success = gemini_service.queue_message(
                message=message_text,
                message_id=message_id,
                client_id=client_id,
                include_image=include_image,
                capture_info=capture_info,
                add_to_existing=add_to_existing,
            )
            
            # Acknowledge receipt
            emit('gemini_message_sent', {
                'success': success,
                'message_id': message_id,
                'timestamp': time.time(),
                'capture_info': capture_info,  # Include capture info in acknowledgment
                'include_image': include_image
            })
          
            
        except (ValueError, FileNotFoundError) as e:
            error_msg = f"Error processing image: {str(e)}"
            client_logger.error(error_msg)
            emit('gemini_error', {
                "error": error_msg,
                "id": message_id,
                "type": "image_error",
                "timestamp": time.time(),
                "frame_url": frame_url,
                "client_id": client_id
            })
            return
            
    except Exception as e:
        error_msg = f"Error in gemini_message handler: {str(e)}"
        client_logger.error(f"{error_msg}\n{traceback.format_exc()}")
        emit('gemini_error', {
            "error": error_msg,
            "id": message_id if 'message_id' in locals() else data.get('id', 'unknown'),
            "timestamp": time.time(),
            "client_id": request.sid
        })

@socketio.on('gemini_message_with_system')
def handle_gemini_message_with_system(data):
    """Handle text message to Gemini with system instructions"""
    if not gemini_service:
        emit('gemini_error', {
            'message': 'Gemini service not available',
            'timestamp': time.time()
        })
        return
    
    text = data.get('text', '')
    client_id = request.sid
    client_info = active_clients.get(client_id, {'ip': 'unknown', 'browser': 'unknown'})
    
    # Check if custom system instructions are provided
    custom_instructions = data.get('system_instructions', None)
    if custom_instructions:
        # Temporarily set system instructions
        original_instructions = gemini_service.system_instructions
        gemini_service.set_system_instructions(custom_instructions)
        success = gemini_service.send_text_with_system_instructions(text, client_id)
        # Restore original instructions
        gemini_service.set_system_instructions(original_instructions)
    else:
        # Use default loaded system instructions
        success = gemini_service.send_text_with_system_instructions(text, client_id)
    
    # Acknowledge receipt
    emit('gemini_message_sent', {
        'success': success,
        'timestamp': time.time(),
        'with_system': True
    })

@socketio.on('gemini_capture')
def handle_gemini_capture():
    """Capture frame for Gemini"""
    if not gemini_service:
        emit('gemini_error', {
            'message': 'Gemini service not available',
            'timestamp': time.time()
        })
        return
    
    success = gemini_service.capture_frame()
    
    # Acknowledge receipt
    emit('gemini_capture_sent', {
        'success': success,
        'timestamp': time.time()
    })

@socketio.on('check_gemini_connection')
def handle_check_gemini_connection():
    """Check and report Gemini connection status"""
    global last_status_log_time
    current_time = time.time()
    
    # Rate limit logging of status checks
    if current_time - last_status_log_time > STATUS_LOG_INTERVAL:
        client_logger.debug(f"[CLIENT] Connection status requested, active clients: {len(active_clients)}")
        last_status_log_time = current_time
    
    connected = False
    if gemini_service:
        # Try to ensure connection is active
        gemini_service.ensure_connection()
        connected = gemini_service.is_connected()
    
    emit('gemini_connection_status', {
        'connected': connected,
        'timestamp': time.time()
    })

@socketio.on('gemini_clear_conversation')
def handle_gemini_clear_conversation(data):
    """Handle clear conversation requests"""
    client_id = data.get('client_id')
    
    # Clear client session in Gemini service if available
    if gemini_service and client_id:
        if hasattr(gemini_service, 'client_sessions') and client_id in gemini_service.client_sessions:
            gemini_service.client_sessions[client_id] = {}
            logger.info(f"Cleared Gemini conversation for client {client_id}")
    
    emit('gemini_response', {
        'type': 'status',
        'content': 'Conversation cleared',
        'success': True,
        'timestamp': time.time()
    })

# ============================================================================
# FLASK ROUTE HANDLERS
# ============================================================================

# Static routes
@app.route('/')
def serve_index():
    return send_from_directory('dist', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('dist', path)

# Media routes
@app.route('/amjpeg', methods=['GET'])
def serve_image():
    try:
        file_path = os.path.join(os.getcwd(), '../output.jpg')
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='image/jpg')
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        logging.error(f"Error serving image: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/shared_frame', methods=['GET'])
def get_latest_frame():
    """Serve the latest frame from the simulation"""
    try:
        # Check if file exists and is recent
        if os.path.exists(GEMINI_FRAME_PATH):
            return send_file(GEMINI_FRAME_PATH, mimetype='image/jpeg')
        else:
            return jsonify({'error': 'No frame available'}), 404
    except Exception as e:
        logging.error(f"Error serving frame: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/video/<string:video_type>/<path:filename>')
def serve_video(video_type, filename):
    try:
        if video_type == 'raw':
            folder = RAW_VIDEO_FOLDER
        elif video_type == 'trimmed':
            folder = TRIMMED_VIDEO_FOLDER
        elif video_type == 'renders':
            folder = RENDERS_FOLDER
        else:
            return jsonify({'error': 'Invalid video type'}), 400
            
        folder_path = os.path.abspath(folder)
        filename = filename.rstrip('/')
        file_path = os.path.join(folder_path, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
            
        if not os.path.commonprefix([folder_path, os.path.abspath(file_path)]) == folder_path:
            return jsonify({'error': 'Invalid path'}), 403
            
        return send_file(file_path)
        
    except Exception as e:
        logging.error(f"Error serving video: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/downloads/<path:filename>')
def download_file(filename):
    try:
        downloads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../motivo/downloads'))
        os.makedirs(downloads_dir, exist_ok=True)
        return send_from_directory(downloads_dir, filename)
    except Exception as e:
        logging.error(f"Error serving download file: {str(e)}")
        return jsonify({'error': str(e)}), 404

# API routes
@app.route('/generate-reward', methods=['POST'])
def generate_reward():
    
    session_id = request.json.get('sessionId', str(datetime.now().timestamp()))
    prompt = request.json.get('prompt')
    
    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400
    
    if not anthropic:
        return jsonify({'error': 'Anthropic API key not configured. Please provide a valid API key in the environment variables.'}), 503
    
    try:
        if session_id not in chat_histories:
            chat_histories[session_id] = []
        
        message = anthropic.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1024,
            system=SYSTEM_INSTRUCTIONS,
            messages=[
                *chat_histories[session_id],
                {
                    "role": "user",
                    "content": f"Generate a reward configuration that achieves this behavior: {prompt}"
                }
            ]
        )
        
        response_content = message.content[0].text if isinstance(message.content, list) else message.content
        
        chat_histories[session_id].extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response_content}
        ])
        
        return jsonify({
            'reward_config': response_content,
            'sessionId': session_id,
            'conversation': chat_histories[session_id]
        })
        
    except Exception as e:
        logging.error(f"Error in generate_reward: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/upload-video', methods=['POST'])
def upload_video():
    if 'video' not in request.files or request.files['video'].filename == '':
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
        
    filename = secure_filename(f"{str(uuid.uuid4())}_{file.filename}")
    filepath = os.path.join(RAW_VIDEO_FOLDER, filename)
    file.save(filepath)
    
    trim_sec = min(max(request.form.get('trim', type=int, default=5), 1), 15)
    start_sec = max(request.form.get('start', type=float, default=0), 0)
    
    try:
        probe = ffmpeg.probe(filepath)
        duration = float(probe['streams'][0]['duration'])
        
        if start_sec + trim_sec > duration:
            return jsonify({
                'error': 'Invalid trim parameters',
                'video_duration': duration,
                'requested_duration': start_sec + trim_sec
            }), 400
        
        trimmed_filename = f"trimmed_{filename}"
        trimmed_filepath = os.path.join(TRIMMED_VIDEO_FOLDER, trimmed_filename)
        
        ffmpeg.input(filepath).output(
            trimmed_filepath,
            r=30,
            ss=start_sec,
            t=trim_sec,
            vsync='cfr'
        ).run()
        
        video_url = f'{VITE_API_URL}/video/trimmed/{trimmed_filename}'
        
        print(f"Video URL: {video_url}")
        print(f"VITE_VIBE_URL: {VITE_VIBE_URL}")
        
        response = requests.post(
            f'{VITE_VIBE_URL}/predictions',
            headers={'accept': 'application/json', 'Content-Type': 'application/json'},
            json={
                "input": {
                    "media": video_url,
                    "render_video": True
                }
            },
            timeout=600
        )

        response.raise_for_status()
        response_data = response.json()
        
        render_url = None
        if 'output' in response_data and 'video' in response_data['output']:
            import base64
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            render_filename = f"render_{timestamp}_{filename}"
            render_filepath = os.path.join(RENDERS_FOLDER, render_filename)
            
            # Get base64 data and handle padding
            b64_data = response_data['output']['video']
            # Add padding if needed
            padding = len(b64_data) % 4
            if padding:
                b64_data += '=' * (4 - padding)
                
            try:
                # Remove any potential data URL prefix
                if ',' in b64_data:
                    b64_data = b64_data.split(',')[1]
                
                # Decode and save base64 video
                video_data = base64.b64decode(b64_data)
                with open(render_filepath, 'wb') as f:
                    f.write(video_data)
                
                render_url = f'{VITE_API_URL}/video/renders/{render_filename}'
                response_data['output']['video_url'] = render_url
                logging.info(f"Successfully saved rendered video to {render_filepath}")
                
            except Exception as e:
                logging.error(f"Error decoding base64 data: {str(e)}")
                logging.debug(f"First 100 chars of b64 data: {b64_data[:100]}")
        else:
            logging.warning("No video data found in response")
            logging.debug(f"Available keys in output: {response_data.get('output', {}).keys()}")
        
        return json.dumps({
            'success': True,
            'video_url': video_url,
            'render_url': render_url,
            'prediction': response_data,
            'video_info': {
                'original_duration': duration,
                'trim_start': start_sec,
                'trim_duration': trim_sec
            }
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()  # Print full traceback
        return jsonify({"error": str(e)}), 500

@app.route('/clear-chat', methods=['POST'])
def clear_chat():
    try:
        session_id = request.json.get('sessionId')
        if session_id and session_id in chat_histories:
            chat_histories[session_id] = []
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error clearing chat: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Database routes - keep both API routes for backward compatibility
# Original routes
@app.route('/conf', methods=['GET'])
@app.route('/api/conf', methods=['GET'])
def get_configs():
    try:
        configs = Content.get_all()
        return jsonify(configs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conf', methods=['POST'])
def create_config():
    try:
        data = request.json
        config_id = Content.add(
            title=data['title'],
            thumbnail=data['thumbnail'],
            type=data['type'],
            data=data['data'],
            cache_file_path=data.get('cache_file_path'),
            tags=data.get('tags', []),
            users=data.get('users', [])
        )
        return jsonify({'id': config_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/conf/<int:config_id>', methods=['PUT'])
@app.route('/api/conf/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    try:
        data = request.json
        update_data = {k: v for k, v in data.items() if v is not None}
        Content.update_content(config_id, **update_data)
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Error updating configuration: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/conf/<int:config_id>', methods=['DELETE'])
@app.route('/api/conf/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    try:
        Content.delete_item(config_id)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error deleting configuration: {str(e)}")
        return jsonify({'error': str(e)}), 500

# New routes with /api/presets
@app.route('/api/presets', methods=['GET'])
def get_presets():
    try:
        presets = Content.get_all()
        return jsonify(presets)
    except Exception as e:
        logging.error(f"Error fetching presets: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/presets', methods=['POST'])
def create_preset():
    try:
        data = request.json
        preset_id = Content.add(
            title=data['title'],
            thumbnail=data['thumbnail'],
            type=data['type'],
            data=data['data'],
            cache_file_path=data.get('cache_file_path'),
            tags=data.get('tags', []),
            users=data.get('users', [])
        )
        return jsonify({'id': preset_id}), 201
    except Exception as e:
        logging.error(f"Error creating preset: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/presets/<int:preset_id>', methods=['PUT'])
def update_preset(preset_id):
    try:
        data = request.json
        update_data = {k: v for k, v in data.items() if v is not None}
        Content.update_content(preset_id, **update_data)
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Error updating preset: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/presets/<int:preset_id>', methods=['DELETE'])
def delete_preset(preset_id):
    try:
        Content.delete_item(preset_id)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error deleting preset: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Utility routes
@app.route('/api/version', methods=['GET'])
def get_version():
    return jsonify({'version': '1.0.0'})

@app.route('/api/ping', methods=['GET'])
def ping():
    """Simple endpoint for testing connectivity"""
    return jsonify({
        "status": "ok",
        "message": "WebServer is running",
        "timestamp": datetime.now().isoformat()
    })

# New route to trigger AI prompt via HTTP POST
@app.route('/api/trigger-general-ai-prompt', methods=['POST'])
def trigger_ai_prompt_http():
    """Receive trigger via HTTP POST and emit a specific Socket.IO event."""
    client_ip = request.remote_addr
    client_logger.info(f"Received HTTP trigger from IP: {client_ip}")
    
    # Extract optional prompt from request JSON body
    custom_prompt = None
    if request.is_json:
        data = request.get_json()
        custom_prompt = data.get('prompt') if isinstance(data, dict) else None
        if custom_prompt:
             client_logger.info(f"Received custom prompt: '{custom_prompt[:50]}...'") # Log first 50 chars
        else:
             client_logger.info("No custom prompt provided in request.")

    try:
        # Emit a specific event that the GeminiSocketService will listen for
        socketio.emit('trigger_ai_prompt', {
            'message': 'Triggering AI prompt from HTTP request',
            'prompt': custom_prompt, # Include the custom prompt (or None)
            'timestamp': time.time()
        })
        client_logger.info("Emitted 'trigger_ai_prompt' event via Socket.IO")
        return jsonify({'success': True, 'prompt_received': bool(custom_prompt)}), 200
    except Exception as e:
        client_logger.error(f"Failed to emit 'trigger_ai_prompt' event: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
if __name__ == '__main__':
    try:
        socketio.run(app, host='0.0.0.0', port=5002, debug=True, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        if gemini_service:
            gemini_service.stop()