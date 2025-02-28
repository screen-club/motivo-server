from flask import Blueprint, request, jsonify, send_from_directory, Response
import os
import json
import logging
from ffmpeg_streamer import FFmpegStreamer

# Setup logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('stream_routes')

# Create Blueprint for streaming routes
stream_bp = Blueprint('stream', __name__)

# Create FFmpeg streamer instance
ffmpeg_streamer = None

# Directory for stream output
STREAM_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../stream_output')

def init_streamer(width=640, height=480, fps=30, quality="medium"):
    """Initialize the FFmpeg streamer with specified settings"""
    global ffmpeg_streamer
    
    # Create output directory if it doesn't exist
    os.makedirs(STREAM_OUTPUT_DIR, exist_ok=True)
    
    # Initialize streamer
    ffmpeg_streamer = FFmpegStreamer(
        width=width,
        height=height,
        fps=fps,
        quality=quality,
        output_dir=STREAM_OUTPUT_DIR
    )
    
    logger.info(f"Initialized FFmpeg streamer with {width}x{height} @ {fps}fps, {quality} quality")
    return ffmpeg_streamer

# Initialize streamer with default settings
init_streamer()

@stream_bp.route('/status', methods=['GET'])
def get_stream_status():
    """Get current streaming status"""
    if ffmpeg_streamer is None:
        return jsonify({"error": "Streamer not initialized"}), 500
        
    status = ffmpeg_streamer.get_streaming_status()
    return jsonify(status)

@stream_bp.route('/start', methods=['POST'])
def start_streaming():
    """Start streaming with specified settings"""
    if ffmpeg_streamer is None:
        return jsonify({"error": "Streamer not initialized"}), 500
        
    try:
        data = request.json or {}
        
        # Get stream type from request
        stream_type = data.get('stream_type', 'hls')
        if stream_type not in ['rtmp', 'hls', 'dash']:
            return jsonify({"error": f"Invalid stream type: {stream_type}"}), 400
            
        # For RTMP, we need a URL
        if stream_type == 'rtmp':
            rtmp_url = data.get('rtmp_url')
            stream_key = data.get('stream_key')
            
            if not rtmp_url:
                return jsonify({"error": "RTMP URL is required for RTMP streaming"}), 400
                
            # Set RTMP URL
            ffmpeg_streamer.set_rtmp_url(rtmp_url, stream_key)
        
        # Start streaming
        stream_info = ffmpeg_streamer.start_streaming(stream_type)
        
        # Add base URL for HLS/DASH
        if stream_type in ['hls', 'dash']:
            host_url = request.host_url.rstrip('/')
            stream_info['full_url'] = f"{host_url}{stream_info['url']}"
        
        return jsonify({
            "success": True,
            "message": f"Streaming started with {stream_type}",
            "stream_info": stream_info
        })
        
    except Exception as e:
        logger.error(f"Error starting stream: {str(e)}")
        return jsonify({"error": str(e)}), 500

@stream_bp.route('/stop', methods=['POST'])
def stop_streaming():
    """Stop the current stream"""
    if ffmpeg_streamer is None:
        return jsonify({"error": "Streamer not initialized"}), 500
        
    try:
        ffmpeg_streamer.stop_streaming()
        return jsonify({
            "success": True,
            "message": "Streaming stopped"
        })
        
    except Exception as e:
        logger.error(f"Error stopping stream: {str(e)}")
        return jsonify({"error": str(e)}), 500

@stream_bp.route('/settings', methods=['PUT'])
def update_settings():
    """Update streamer settings"""
    if ffmpeg_streamer is None:
        return jsonify({"error": "Streamer not initialized"}), 500
        
    try:
        data = request.json or {}
        
        # Check for quality setting
        if 'quality' in data:
            quality = data['quality']
            if quality not in ['medium', 'high']:
                return jsonify({"error": f"Invalid quality: {quality}"}), 400
                
            success = ffmpeg_streamer.set_quality(quality)
            if not success:
                return jsonify({"error": "Failed to set quality"}), 500
        
        # Get current settings
        status = ffmpeg_streamer.get_streaming_status()
        
        return jsonify({
            "success": True,
            "message": "Settings updated",
            "settings": status
        })
        
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        return jsonify({"error": str(e)}), 500

@stream_bp.route('/reset', methods=['POST'])
def reset_streamer():
    """Reset the streamer with new settings"""
    try:
        data = request.json or {}
        
        width = data.get('width', 640)
        height = data.get('height', 480)
        fps = data.get('fps', 30)
        quality = data.get('quality', 'medium')
        
        # Stop existing streamer if running
        if ffmpeg_streamer is not None:
            if ffmpeg_streamer.is_streaming:
                ffmpeg_streamer.stop_streaming()
        
        # Initialize new streamer
        streamer = init_streamer(width, height, fps, quality)
        
        return jsonify({
            "success": True,
            "message": "Streamer reset with new settings",
            "settings": {
                "width": width,
                "height": height,
                "fps": fps,
                "quality": quality
            }
        })
        
    except Exception as e:
        logger.error(f"Error resetting streamer: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Routes to serve HLS/DASH stream files
@stream_bp.route('/hls/<path:filename>')
def serve_hls(filename):
    """Serve HLS stream files"""
    try:
        return send_from_directory(os.path.join(STREAM_OUTPUT_DIR, 'hls'), filename)
    except Exception as e:
        logger.error(f"Error serving HLS file: {str(e)}")
        return jsonify({"error": str(e)}), 500

@stream_bp.route('/dash/<path:filename>')
def serve_dash(filename):
    """Serve DASH stream files"""
    try:
        return send_from_directory(os.path.join(STREAM_OUTPUT_DIR, 'dash'), filename)
    except Exception as e:
        logger.error(f"Error serving DASH file: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Function to update the frame from simulation
def update_frame(frame):
    """Update the current frame to be streamed"""
    if ffmpeg_streamer is not None:
        ffmpeg_streamer.update_frame(frame)
    else:
        logger.warning("Attempted to update frame but streamer is not initialized") 