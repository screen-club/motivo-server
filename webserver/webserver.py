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
        file_path = os.path.join(os.getcwd(), '../output.jpg')
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='image/jpg')
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        print(f"Error serving image: {str(e)}")
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
        print(f"Error serving frame: {str(e)}")
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
        print(f"Error serving video: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/downloads/<path:filename>')
def download_file(filename):
    try:
        downloads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../motivo/downloads'))
        print(f"Looking for file in: {downloads_dir}")
        os.makedirs(downloads_dir, exist_ok=True)
        return send_from_directory(downloads_dir, filename)
    except Exception as e:
        print(f"Error serving download file: {str(e)}")
        return jsonify({'error': str(e)}), 404

# API routes
@app.route('/generate-reward', methods=['POST'])
def generate_reward():
    print("\n=== New Request ===")
    
    session_id = request.json.get('sessionId', str(datetime.now().timestamp()))
    prompt = request.json.get('prompt')
    
    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400
    
    try:
        if session_id not in chat_histories:
            chat_histories[session_id] = []
        
        print(f"Sending prompt: {prompt}")
        print(f"System instructions length: {len(SYSTEM_INSTRUCTIONS)}")
        
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
        
        print(f"Raw message response: {message}")
        print(f"Message content: {message.content}")
        
        response_content = message.content[0].text if isinstance(message.content, list) else message.content
        
        print(f"Final response content: {response_content}")
        
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
        print(f"Error in generate_reward: {str(e)}")
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

        print(f"Response: {response}")
        response.raise_for_status()
        response_data = response.json()
        
        # Debug print to see response structure
        print("Response data:", json.dumps(response_data, indent=2))
        
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
                print(f"Successfully saved rendered video to {render_filepath}")
                
            except Exception as e:
                print(f"Error decoding base64 data: {str(e)}")
                print(f"First 100 chars of b64 data: {b64_data[:100]}")
        else:
            print("No video data found in response")
            print("Available keys in output:", response_data.get('output', {}).keys())
        
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
        print(f"Error clearing chat: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Database routes
@app.route('/api/conf', methods=['GET'])
def get_configs():
    try:
        db = Content()
        configs = db.get_all()  # This will now include tags from our updated model
        return jsonify(configs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conf', methods=['POST'])
def create_config():
    try:
        data = request.json
        db = Content()
        config_id = db.add(
            title=data['title'],
            thumbnail=data['thumbnail'],
            type=data['type'],  # vibe/reward/llm
            data=data['data'],  # json object
            cache_file_path=data.get('cache_file_path'),  # Optional field
            tags=data.get('tags', []),  # Optional tags field, defaults to empty list
            users=data.get('users', [])  # Optional users field, defaults to empty list
        )
        return jsonify({'id': config_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conf/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    try:
        data = request.json
        db = Content()
        
        # Remove any None values from the data
        update_data = {k: v for k, v in data.items() if v is not None}
        
        # Update the configuration
        updated_config = db.update_content(config_id, **update_data)
        
        return jsonify(updated_config)
        
    except Exception as e:
        print(f"Error updating configuration: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/conf/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    try:
        db = Content()
        db.deleteItem(config_id)
        return jsonify({'success': True})
    except Exception as e:
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

@app.route('/api/generate-position', methods=['POST'])
def generate_position():
    """Generate a position configuration using Gemini and system instructions"""
    try:
        if not gemini_service:
            return jsonify({'error': 'Gemini service not available'}), 503
        
        # Get the prompt from the request
        data = request.json
        if not data or 'prompt' not in data:
            return jsonify({'error': 'Missing prompt in request'}), 400
        
        prompt = data['prompt']
        
        # Load the system instructions file if needed
        if not gemini_service.system_instructions:
            success = gemini_service.load_system_instructions()
            if not success:
                return jsonify({'error': 'Failed to load system instructions'}), 500
        
        # Create a unique ID for this request to track the response
        request_id = str(uuid.uuid4())
        
        # Send the text with system instructions
        modified_prompt = f'Generate a position configuration that achieves this pose: "{prompt}"'
        success = gemini_service.send_text_with_system_instructions(modified_prompt, request_id)
        
        if not success:
            return jsonify({'error': 'Failed to send request to Gemini API'}), 500
        
        # Wait for the response with a timeout
        start_time = time.time()
        response = None
        timeout = 20  # seconds
        
        while time.time() - start_time < timeout:
            # Process incoming messages
            latest_responses = []
            
            def collect_response(msg):
                nonlocal response
                # Check if it's a text response
                if msg.get('type') == 'gemini_response':
                    latest_responses.append(msg)
                    # If the response is complete, save it
                    if msg.get('complete', False):
                        response = msg.get('content', '')
            
            # Process any messages that came in
            gemini_service.process_incoming_messages(collect_response)
            
            # If we have a response, break out of the loop
            if response:
                break
            
            # Sleep briefly to avoid maxing out CPU
            time.sleep(0.1)
        
        # Check if we got a response
        if not response:
            return jsonify({'error': 'Timed out waiting for response'}), 504
        
        # Try to parse the response as JSON
        try:
            # Extract JSON from the response if needed (sometimes the model might output extra text)
            import re
            json_match = re.search(r'(\{[\s\S]*\})', response)
            if json_match:
                json_str = json_match.group(1)
                position_data = json.loads(json_str)
            else:
                position_data = json.loads(response)
                
            return jsonify({
                'success': True,
                'position': position_data
            })
        except json.JSONDecodeError as e:
            return jsonify({
                'error': 'Failed to parse JSON response',
                'raw_response': response,
                'message': str(e)
            }), 422
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/connection-status', methods=['GET'])
def get_connection_status():
    """Return connection status information for monitoring"""
    try:
        # Get unique client count
        unique_ips = set(client['ip'] for client in active_clients.values())
        clients_by_browser = {}
        for client in active_clients.values():
            browser = client.get('browser', 'Unknown')
            if browser not in clients_by_browser:
                clients_by_browser[browser] = 0
            clients_by_browser[browser] += 1
        
        # Get Gemini service status
        gemini_status = {
            'connected': False,
            'state': 'not_initialized',
            'uptime': 0
        }
        
        if gemini_service:
            gemini_status['connected'] = gemini_service.is_connected()
            gemini_status['state'] = getattr(gemini_service, 'connection_state', 'unknown')
            
            # Calculate uptime if available
            if hasattr(gemini_service, 'last_connection_attempt') and gemini_service.is_connected():
                gemini_status['uptime'] = time.time() - gemini_service.last_connection_attempt
            
            # Get detailed health if available
            if hasattr(gemini_service, 'connection_health'):
                gemini_status.update(gemini_service.connection_health())
        
        # Calculate actual server uptime
        server_uptime = time.time() - SERVER_START_TIME
        
        return jsonify({
            'server': {
                'started_at': SERVER_START_TIME,
                'uptime': server_uptime,
                'uptime_formatted': f"{int(server_uptime // 3600)}h {int((server_uptime % 3600) // 60)}m {int(server_uptime % 60)}s"
            },
            'clients': {
                'active_connections': len(active_clients),
                'unique_users': len(unique_ips),
                'by_browser': clients_by_browser,
                'unique_ips': list(unique_ips)
            },
            'gemini': gemini_status,
            'timestamp': time.time()
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
if __name__ == '__main__':
    try:
        socketio.run(app, host='0.0.0.0', port=5002, debug=True, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logger.info("Shutting down due to keyboard interrupt")
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}", exc_info=True)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())