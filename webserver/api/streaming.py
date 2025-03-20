from flask import Blueprint, request, jsonify, send_from_directory, Response
import os
import json
import logging
from pathlib import Path
from webserver.services.streaming import FFmpegStreamer

# Setup logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('stream_routes')

# Create Blueprint for streaming routes
stream_bp = Blueprint('stream', __name__)

# Get path to public storage
base_dir = str(Path(__file__).resolve().parents[3])
public_storage_dir = os.path.join(base_dir, 'public', 'storage')

# Directory for stream output
STREAM_OUTPUT_DIR = os.path.join(public_storage_dir, 'streams')
os.makedirs(STREAM_OUTPUT_DIR, exist_ok=True)

# Create FFmpeg streamer instance
ffmpeg_streamer = FFmpegStreamer(output_dir=STREAM_OUTPUT_DIR)

@stream_bp.route('/stream/status', methods=['GET'])
def get_stream_status():
    """Get the status of all active streams"""
    status = {
        "is_streaming": ffmpeg_streamer.is_streaming,
        "active_formats": list(ffmpeg_streamer.active_formats.keys()),
        "output_dir": ffmpeg_streamer.output_dir
    }
    return jsonify(status)

@stream_bp.route('/stream/start', methods=['POST'])
def start_stream():
    """Start streaming with specified formats"""
    try:
        data = request.json
        formats = data.get('formats', ['hls'])  # Default to HLS if not specified
        width = data.get('width', 640)
        height = data.get('height', 480)
        fps = data.get('fps', 30)
        
        # Update streamer settings
        ffmpeg_streamer.width = width
        ffmpeg_streamer.height = height
        ffmpeg_streamer.fps = fps
        
        # Start streaming
        ffmpeg_streamer.start_streaming(formats)
        
        return jsonify({
            "success": True,
            "message": f"Streaming started with formats: {formats}",
            "stream_info": {
                "formats": formats,
                "resolution": f"{width}x{height}",
                "fps": fps
            }
        })
    except Exception as e:
        logger.error(f"Error starting stream: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@stream_bp.route('/stream/stop', methods=['POST'])
def stop_stream():
    """Stop all active streams"""
    try:
        ffmpeg_streamer.stop_streaming()
        return jsonify({
            "success": True,
            "message": "All streams stopped"
        })
    except Exception as e:
        logger.error(f"Error stopping stream: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@stream_bp.route('/stream/hls/<path:filename>')
def serve_hls_stream(filename):
    """Serve HLS stream files"""
    hls_dir = os.path.join(STREAM_OUTPUT_DIR, 'hls')
    return send_from_directory(hls_dir, filename)

@stream_bp.route('/stream/dash/<path:filename>')
def serve_dash_stream(filename):
    """Serve DASH stream files"""
    dash_dir = os.path.join(STREAM_OUTPUT_DIR, 'dash')
    return send_from_directory(dash_dir, filename)

@stream_bp.route('/amjpeg')
def serve_mjpeg_stream():
    """Serve MJPEG stream (fallback for clients not using WebRTC)"""
    # Get the path to the latest frame
    frame_path = os.path.join(public_storage_dir, 'shared_frames', 'latest_frame.jpg')
    
    if os.path.exists(frame_path):
        return send_from_directory(os.path.join(public_storage_dir, 'shared_frames'), 'latest_frame.jpg')
    else:
        # If no frame is available, return a placeholder
        return jsonify({
            "success": False,
            "error": "No frame available"
        }), 404

@stream_bp.route('/stream/thumbnail')
def get_latest_thumbnail():
    """Get the latest thumbnail image from the stream"""
    thumbnail_path = os.path.join(STREAM_OUTPUT_DIR, 'thumbnail.jpg')
    if os.path.exists(thumbnail_path):
        return send_from_directory(STREAM_OUTPUT_DIR, 'thumbnail.jpg')
    else:
        return jsonify({
            "success": False,
            "error": "No thumbnail available"
        }), 404

# Initialize stream directory
os.makedirs(os.path.join(STREAM_OUTPUT_DIR, 'hls'), exist_ok=True)
os.makedirs(os.path.join(STREAM_OUTPUT_DIR, 'dash'), exist_ok=True)