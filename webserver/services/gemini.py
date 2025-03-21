import asyncio
import base64
import json
import os
import traceback
import time
import requests
import websockets
import threading
import uuid
from queue import Queue
import logging
from pathlib import Path

# Set up logging
logger = logging.getLogger("gemini_service")
logger.setLevel(logging.WARNING)  # Only log warnings and errors

class GeminiService:
    """Service for interacting with Google's Gemini API via WebSockets"""
    
    def __init__(self, api_key=None, model="gemini-2.0-flash-exp", port=5002):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY environment variable not set")
            
        self.model = model
        self.port = port
        self.host = "generativelanguage.googleapis.com"
        self.uri = f"wss://{self.host}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={self.api_key}"
        
        # WebSocket connection
        self.ws = None
        self.ws_lock = threading.Lock()
        
        # Runtime management
        self.running = False
        self.thread = None
        self.loop = None
        
        # Client sessions
        self.client_sessions = {}
        
        # Message queues
        self.outgoing_queue = Queue()
        self.incoming_queue = Queue()
        
        # Storage paths
        self.base_dir = str(Path(__file__).resolve().parents[3])
        
        # Define paths based on the structure
        if os.path.exists(os.path.join(self.base_dir, 'motivo-server')):
            # We're in the liminal/motivo-server structure
            self.motivo_server_dir = os.path.join(self.base_dir, 'motivo-server')
        else:
            # We're directly in motivo-server
            self.motivo_server_dir = self.base_dir
            
        self.public_storage_dir = os.path.join(self.motivo_server_dir, 'public', 'storage')
        self.shared_frames_dir = os.path.join(self.public_storage_dir, 'shared_frames')
        
        # Ensure directories exist
        os.makedirs(self.shared_frames_dir, exist_ok=True)
        
        # Connection state tracking
        self.connection_state = "disconnected"
        self.last_connection_attempt = 0
        self.connection_attempts = 0
        
        # System instructions
        self.system_instructions = None
        self.system_instructions_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'system_instructions.txt')
        
        logger.info(f"Gemini service initialized with port {port}")
    
    def load_system_instructions(self):
        """Load system instructions from file"""
        try:
            if os.path.exists(self.system_instructions_path):
                with open(self.system_instructions_path, 'r', encoding='utf-8') as f:
                    self.system_instructions = f.read().strip()
                logger.info(f"Loaded system instructions ({len(self.system_instructions)} characters)")
            else:
                logger.warning(f"System instructions file not found: {self.system_instructions_path}")
                self.system_instructions = None
        except Exception as e:
            logger.error(f"Error loading system instructions: {str(e)}")
            self.system_instructions = None
            
    def _broadcast_connection_status(self, is_connected):
        """Helper method to broadcast connection status"""
        pass
    
    def start(self):
        """Start the Gemini service"""
        if self.thread is None:
            self.running = True
            
            # Load system instructions if available
            self.load_system_instructions()
            
            self.thread = threading.Thread(target=self._run_async_loop)
            self.thread.daemon = True
            self.thread.start()
            logger.info("Gemini service started in background thread")
            

    def queue_message(self, message, message_id=None, client_id=None, include_image=True, capture_info=None, add_to_existing=False, auto_capture=False):

        """Queue a message to be sent to Gemini"""
        if message_id is None:
            message_id = str(uuid.uuid4())
            
        if client_id is None:
            client_id = "system"
        
        # Store message-id mapping for this client
        if client_id not in self.client_sessions:
            self.client_sessions[client_id] = {}
            
        # Always track the last message ID for this client
        self.client_sessions[client_id]["last_message_id"] = message_id
        logger.info(f"Associating client {client_id} with message ID {message_id}")
        
        # Ensure the service is running
        if not self.running:
            self.start()
        
        # CRITICAL: Handle image to send with Gemini request
        if include_image:
            # Require capture_info when include_image is True
            if not capture_info:
                error_msg = "Error: include_image is True but no capture_info provided"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Verify the image file exists
            if not os.path.exists(capture_info['fullpath']):
                error_msg = f"Error: Image file not found at {capture_info['fullpath']}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
                
            # No longer store in self.last_image - send directly
            logger.info(f"Using image from capture_info: {capture_info['path']}")
        
        # Log if this is an auto-capture message
        if auto_capture:
            logger.info("Processing auto-capture message - will preserve existing rewards")
        
        # Send the text to Gemini, optionally including the image from capture_info
        self.send_text(message, message_id, client_id, include_image, capture_info, add_to_existing, auto_capture)
        
        return message_id
        
    def send_text(self, text, message_id, client_id=None, include_image=True, capture_info=None, add_to_existing=False, auto_capture=False):
        """Send text message to Gemini API, optionally with the provided image"""
        if not self.running:
            self.start()
        
        # Check if we have a connection
        has_connection = False
        with self.ws_lock:
            has_connection = self.ws is not None
            
        if not has_connection:
            logger.info("No active connection detected, attempting to reconnect")
            self.ensure_connection()
          
                
            return True
        
        try:
            # Prepare message parts
            parts = [{"text": text}]
            
            # Check if we should include an image
            if include_image:
                # Verify we have valid capture_info
                if not capture_info or not capture_info.get("fullpath"):
                    error_msg = "Image inclusion requested, but no valid capture_info provided"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                
                # Use the image path directly from capture_info
                image_path = capture_info.get("fullpath")
                
                if not os.path.exists(image_path):
                    error_msg = f"Image file not found at path: {image_path}"
                    logger.error(error_msg)
                    raise FileNotFoundError(error_msg)
                
                try:
                    # Read the image data directly from the provided path
                    with open(image_path, 'rb') as f:
                        image_data = f.read()
                        
                    # Convert to base64
                    import base64
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                    
                    # Add image part before text
                    parts.insert(0, {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64
                        }
                    })
                    
                    logger.info(f"Added image to message: {image_path}")
                    
                except Exception as img_err:
                    error_msg = f"Failed to process image: {str(img_err)}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
            
            # Format the message according to Gemini Multimodal Live API documentation
            msg = {
                "clientContent": {
                    "turns": [
                        {
                            "role": "user",
                            "parts": parts
                        }
                    ],
                    "turn_complete": True
                }
            }
            
            # Add to queue and log
            self.outgoing_queue.put(msg)
            
            # If we only have one client, store this client ID for response routing
            if client_id:
                # Initialize if not exists
                if client_id not in self.client_sessions:
                    self.client_sessions[client_id] = {}
                
                # Update session with message information
                session = self.client_sessions[client_id]
                session.update({
                    "last_message": text,
                    "timestamp": time.time()
                })
                
                # Store message ID and image info together in a dictionary for this specific message
                # This ensures each message keeps track of its own image
                if include_image and capture_info:
                    # Don't store in last_image - create a message-specific record
                    logger.info(f"Storing image {capture_info['path']} for message ID {message_id}")
                    if "message_images" not in session:
                        session["message_image"] = ""
                    
                    session["message_image"] = {
                        "path": capture_info["path"],
                        "timestamp": capture_info["timestamp"],
                        "timestamp_str": capture_info["timestamp_str"]
                    }
            
            # Store the message ID for tracking - don't override the passed message_id
            session["last_message_id"] = message_id
            
            return True
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            traceback.print_exc()
            return False
        
    def _run_async_loop(self):
        """Run the asyncio event loop in a background thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self._connect_and_run())
        except Exception as e:
            logger.error(f"Error in Gemini service loop: {str(e)}")
            traceback.print_exc()
        finally:
            self.loop.close()
            
    async def _connect_and_run(self):
        """Connect to Gemini API and maintain the connection"""
        retry_delay = 1
        max_retry_delay = 30
        
        while self.running:
            try:
                # Check if we should reconnect immediately (based on status check)
                if self.connection_state == "reconnecting":
                    pass
                else:
                    # Handle normal retry delay logic
                    current_time = time.time()
                    time_since_last_attempt = current_time - self.last_connection_attempt
                    
                    if time_since_last_attempt < retry_delay and self.connection_attempts > 1:
                        await asyncio.sleep(0.5)  # Small sleep to prevent tight loop
                        continue
                    
                self.connection_attempts += 1
                self.last_connection_attempt = time.time()
                self.connection_state = "connecting"
                
                # Reload system instructions on each connection attempt
                self.load_system_instructions()
                
                # Verify API key is set
                if not self.api_key:
                    logger.error("Cannot connect to Gemini: API key is not set")
                    self.connection_state = "failed"
                    self._broadcast_connection_status(False)
                    await asyncio.sleep(5)
                    continue
                
                # Try to connect with more detailed error handling
                try:
                    # Use basic headers for the connection
                    headers = {
                        "Content-Type": "application/json",
                        "User-Agent": "GeminiServiceClient/1.0"
                    }
                    
                    # Connect to the Gemini API with shorter timeouts
                    websocket = await websockets.connect(
                        self.uri, 
                        additional_headers=headers,
                        ping_interval=20,
                        ping_timeout=10,  # Increased for more stability
                        close_timeout=5
                    )
                except websockets.exceptions.InvalidStatusCode as status_err:
                    logger.error(f"Invalid status code from Gemini API: {status_err}")
                    if hasattr(status_err, 'status_code'):
                        logger.error(f"Status code: {status_err.status_code}")
                    self.connection_state = "failed"
                    self._broadcast_connection_status(False)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue
                except Exception as conn_err:
                    logger.error(f"Failed to establish WebSocket connection: {str(conn_err)}")
                    self.connection_state = "failed"
                    self._broadcast_connection_status(False)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue
                
                with self.ws_lock:
                    self.ws = websocket
                
                # Reset retry delay on successful connection
                retry_delay = 1
                
                # Send setup message
                try:
                    setup_msg = {
                        "setup": {
                            "model": f"models/{self.model}",
                            "generationConfig": {
                                "responseModalities": ["TEXT"],  # Only request text responses
                                "responseMimeType": "application/json",  # Request JSON output
                                "temperature": 0.7,
                                "topP": 0.95,
                                "topK": 40,
                                "maxOutputTokens": 8192,  # Allow for longer responses
                            }
                        }
                    }
                    
                    # Add system instructions with the correct format
                    if self.system_instructions:
                        setup_msg["setup"]["systemInstruction"] = {
                            "parts": [
                                {
                                    "text": self.system_instructions
                                }
                            ]
                        }
                    
                    await self.ws.send(json.dumps(setup_msg))
                    
                    # Wait for response with timeout
                    try :
                        raw_response = await asyncio.wait_for(self.ws.recv(), timeout=10)
                        setup_response = json.loads(raw_response)
                    
                        # Broadcast successful connection
                        self.connection_state = "connected"
                        self.connection_attempts = 0
                        self._broadcast_connection_status(True)
                    except Exception as e:
                        logger.error(f"Error during Gemini setup")
                        print(e)
                       
                        await self.ws.close()
                        self.ws = None
                        self.connection_state = "setup_failed"
                        self._broadcast_connection_status(False)
                        #await asyncio.sleep(retry_delay)
                except asyncio.TimeoutError:
                    logger.error("Timeout waiting for setup response from Gemini")
                    await self.ws.close()
                    self.ws = None
                    self.connection_state = "timeout"
                    self._broadcast_connection_status(False)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue
                except Exception as setup_err:
                    logger.error(f"Error during Gemini setup")
                    
                    traceback.print_exc()
                    await self.ws.close()
                    self.ws = None
                    self.connection_state = "setup_failed"
                    self._broadcast_connection_status(False)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue
                
                # Process messages with better error handling
                try:
                    await asyncio.gather(
                        self._process_outgoing_queue(),
                        self._process_incoming_messages()
                    )
                except websockets.exceptions.ConnectionClosed as closed_err:
                    logger.warning(f"Gemini WebSocket connection closed with code {closed_err.code}: {closed_err.reason}")
                    self.connection_state = "closed"
                except Exception as process_err:
                    logger.error(f"Error processing messages: {str(process_err)}")
                    self.connection_state = "error"
                    traceback.print_exc()
                
            except Exception as e:
                logger.error(f"Unexpected error in Gemini connection: {str(e)}")
                self.connection_state = "error"
                traceback.print_exc()
                
            finally:
                # Clear the connection in all cases
                with self.ws_lock:
                    if self.ws:
                        try:
                            await self.ws.close()
                        except:
                            logger.warning("Error when closing WebSocket connection")
                        self.ws = None
                
                # Notify of disconnection
                self.connection_state = "disconnected"
                self._broadcast_connection_status(False)
                
                # Wait before reconnecting
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
                
    async def _process_outgoing_queue(self):
        """Process messages from the outgoing queue and send to Gemini"""
        while self.running and self.ws:
            try:
                # Check if there are messages to send
                if not self.outgoing_queue.empty():
                    message = self.outgoing_queue.get()
                    
                    # Send the message
                    serialized = json.dumps(message)
                    try:
                        await self.ws.send(serialized)
                    except websockets.exceptions.ConnectionClosedError as ws_err:
                        logger.warning(f"Connection closed while sending message: {ws_err}")
                        # Break the loop to trigger reconnection
                        break
                
                # Brief pause to prevent high CPU usage
                await asyncio.sleep(0.01)
            
            except websockets.exceptions.ConnectionClosedError as ws_err:
                logger.warning(f"Connection closed in outgoing queue: {ws_err}")
                # Break the loop to trigger reconnection
                break
            except Exception as e:
                logger.error(f"Error processing outgoing message: {str(e)}")
                traceback.print_exc()
                await asyncio.sleep(1)
    
    async def _process_incoming_messages(self):
        """Process incoming messages from Gemini API"""
        current_response = ""  # Buffer to accumulate text chunks
        turn_in_progress = False
        current_message_id = None  # Track which message we're currently processing
        
        while self.running and self.ws:
            try:
                # Receive message from Gemini
                raw_response = await self.ws.recv()
               
                # Parse JSON response
                try:
                    response = json.loads(raw_response)
                    
                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to parse JSON response: {str(json_err)}")
                    continue
                
                # Check for setupComplete
                if "setupComplete" in response:
                    continue
                
                # If this is the start of a new turn, try to get the message ID
                # from the first client in the sessions
                if not turn_in_progress and "serverContent" in response:
                    client_ids = list(self.client_sessions.keys())
                    if client_ids:
                        client_id = client_ids[0]
                        session = self.client_sessions.get(client_id, {})
                        current_message_id = session.get("last_message_id")
                        logger.info(f"Starting to process response for message ID: {current_message_id}")
                    
                
                # Extract text content based on the Gemini Multimodal Live API structure
                text_content = None
                turn_complete = False
                
                # Check for serverContent which contains the model's response
                if "serverContent" in response:
                    server_content = response["serverContent"]
                    
                    # Check for turn completion
                    if server_content.get("turnComplete", False):
                        turn_complete = True
                    
                    # Check for interruption
                    if server_content.get("interrupted", False):
                        current_response = ""  # Clear buffer on interruption
                        turn_in_progress = False
                    
                    # Extract text from modelTurn if present
                    if "modelTurn" in server_content:
                        model_turn = server_content["modelTurn"]
                        if "parts" in model_turn and isinstance(model_turn["parts"], list):
                            for part in model_turn["parts"]:
                                if "text" in part:
                                    text_content = part["text"]
                                    turn_in_progress = True
                                    break
                
                # Accumulate text content if present
                if text_content:
                    current_response += text_content
                
                # Send the response when we get a complete turn or significant chunk
                if (text_content and len(text_content) > 10) or turn_complete:
                    if current_response:
                        # Determine client IDs that should receive this response
                        client_ids = list(self.client_sessions.keys())
                        
                        # Add response to incoming queue for processing
                        response_data = {
                            "type": "gemini_response",
                            "content": current_response,
                            "timestamp": time.time(),
                            "complete": turn_complete,
                            "message_id": current_message_id
                        }
                        
                        # Get image data directly from client session if available
                        if client_ids:  # Remove turn_complete check to include image in all responses
                            client_id = client_ids[0]
                            if client_id in self.client_sessions:
                                session = self.client_sessions[client_id]
                                
                                
                                # Try to find the message-specific image first
                                print("session", session)
                                if "message_image" in session:
                                    
                                    img_info = session["message_image"]
                                   
                                    response_data["image_path"] = img_info["path"]
                                    response_data["image_timestamp"] = img_info["timestamp"]
                                    response_data["timestamp_str"] = img_info["timestamp_str"]
                                    
                                  
                                else:
                                    logger.warning(f"No image found for message ID {current_message_id} when sending response")
                        
                        # Add client info if available
                        if len(client_ids) == 1:
                            response_data["client_id"] = client_ids[0]
                            
                        self.incoming_queue.put(response_data)
                        
                        # Clear the buffer if the turn is complete
                        if turn_complete:
                            current_response = ""
                            turn_in_progress = False
                elif not text_content and not turn_complete:
                    logger.warning("No text content found in response")
                
                # Check for error messages
                if "error" in response:
                    logger.error(f"Gemini API error: {response.get('error')}")
            
            except websockets.exceptions.ConnectionClosed as ws_err:
                logger.warning(f"Gemini WebSocket connection closed: {ws_err}")
                self.connection_state = "closed"
                break
            except Exception as e:
                logger.error(f"Error processing incoming message: {str(e)}")
                traceback.print_exc()
                await asyncio.sleep(1)
    
    def is_connected(self):
        """Check if connected to Gemini API"""
        with self.ws_lock:
            connected = self.ws is not None and self.connection_state == "connected"
        
        return connected
    
    def get_connection_status(self):
        """Get detailed connection status for API endpoints"""
        status = {
            "connected": self.is_connected(),
            "state": self.connection_state
        }
        
        # Always attempt reconnection when status is checked
        if not status["connected"] and self.running:
            # Force immediate reconnection attempt
            self.connection_state = "reconnecting"
            self.last_connection_attempt = 0
            
            status["reconnection_triggered"] = True
        
        return status
    
    def ensure_connection(self):
        """Ensure that the service is connected, triggering connection if needed"""
        if not self.is_connected() and self.running:
            
            # If not already attempting to reconnect
            if self.connection_state not in ["connecting", "reconnecting"]:
                self.connection_state = "reconnecting"
                
                # Reset last connection attempt time to trigger immediate reconnection
                self.last_connection_attempt = 0
                
                # If the thread isn't running, start it
                if self.thread is None or not self.thread.is_alive():
                    self.start()
                    
            return False
        return True
        
    def process_incoming_messages(self, callback):
        """Process any incoming messages and call the provided callback"""
        # Create a module-level reference to the logger to ensure it's always available
        _logger = logging.getLogger("gemini_service")
        
        try:
            while not self.incoming_queue.empty():
                try:
                    message = self.incoming_queue.get_nowait()
                    callback(message)
                except Exception as e:
                    # Use the local logger reference
                    _logger.error(f"Error processing incoming message queue: {str(e)}")
                    traceback.print_exc()
        except Exception as e:
            _logger.error(f"Error in process_incoming_messages: {str(e)}")
            traceback.print_exc()