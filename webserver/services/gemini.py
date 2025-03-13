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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gemini_service")

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
        self.public_storage_dir = os.path.join(self.base_dir, 'public', 'storage')
        self.shared_frames_dir = os.path.join(self.public_storage_dir, 'shared_frames')
        self.gemini_frame_path = os.path.join(self.shared_frames_dir, 'latest_frame.jpg')
        
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
        # This would typically emit a websocket message
        logger.info(f"Connection status: {'connected' if is_connected else 'disconnected'}")
    
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
            
    def queue_message(self, message, message_id=None, client_id=None):
        """Queue a message to be sent to Gemini"""
        if message_id is None:
            message_id = str(uuid.uuid4())
            
        if client_id is None:
            client_id = "system"
        
        # Send the text to Gemini instead of just queuing the raw message
        self.send_text(message, client_id)
            
        logger.debug(f"Queued message {message_id} for client {client_id}")
        return message_id
        
    def send_text(self, text, client_id=None):
        """Send text message to Gemini API"""
        if not self.running:
            logger.warning("Cannot send text - service not running")
            return False
        
        # Check if we have a connection
        with self.ws_lock:
            if not self.ws:
                logger.warning("Cannot send text - no WebSocket connection")
                return False
        
        try:
            # Format the message according to Gemini Multimodal Live API documentation
            msg = {
                "clientContent": {
                    "turns": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": text
                                }
                            ]
                        }
                    ],
                    "turn_complete": True
                }
            }
            
            # Add to queue and log
            self.outgoing_queue.put(msg)
            logger.info(f"Queued text message for Gemini: {text[:50]}...")
            
            # If we only have one client, store this client ID for response routing
            if client_id:
                self.client_sessions[client_id] = {
                    "last_message": text,
                    "timestamp": time.time()
                }
                logger.debug(f"Associated message with client ID: {client_id}")
            
            return True
        except Exception as e:
            logger.error(f"Error sending text message: {str(e)}")
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
            logger.info("Gemini service loop closed")
            
    async def _connect_and_run(self):
        """Connect to Gemini API and maintain the connection"""
        retry_delay = 1
        max_retry_delay = 30
        
        while self.running:
            try:
                self.connection_attempts += 1
                self.last_connection_attempt = time.time()
                self.connection_state = "connecting"
                logger.info(f"[CONNECTIVITY] Connecting to Gemini API (attempt #{self.connection_attempts}, retry delay: {retry_delay}s)")
                
                # Reload system instructions on each connection attempt
                self.load_system_instructions()
                
                # Verify API key is set
                if not self.api_key:
                    logger.error("[CONNECTIVITY] Cannot connect to Gemini: API key is not set")
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
                    
                    # Connect to the Gemini API
                    websocket = await websockets.connect(
                        self.uri, 
                        additional_headers=headers,
                        ping_interval=30,
                        ping_timeout=10
                    )
                    logger.info("[CONNECTIVITY] WebSocket connection established successfully")
                except Exception as conn_err:
                    logger.error(f"[CONNECTIVITY] Failed to establish WebSocket connection: {str(conn_err)}")
                    self.connection_state = "failed"
                    self._broadcast_connection_status(False)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    logger.info(f"[CONNECTIVITY] Will retry connection in {retry_delay} seconds")
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
                        logger.info(f"[CONNECTIVITY] Added system instructions to setup message ({len(self.system_instructions)} chars)")
                    
                    logger.info(f"[CONNECTIVITY] Sending setup message to initialize Gemini connection")
                    await self.ws.send(json.dumps(setup_msg))
                    
                    # Wait for response with timeout
                    raw_response = await asyncio.wait_for(self.ws.recv(), timeout=10)
                    setup_response = json.loads(raw_response)
                    logger.info(f"[CONNECTIVITY] Gemini API setup complete and ready for messages")
                    
                    # Broadcast successful connection
                    self.connection_state = "connected"
                    self.connection_attempts = 0
                    self._broadcast_connection_status(True)
                except asyncio.TimeoutError:
                    logger.error("[CONNECTIVITY] Timeout waiting for setup response from Gemini")
                    await self.ws.close()
                    self.ws = None
                    self.connection_state = "timeout"
                    self._broadcast_connection_status(False)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    logger.info(f"[CONNECTIVITY] Will retry connection in {retry_delay} seconds")
                    continue
                except Exception as setup_err:
                    logger.error(f"[CONNECTIVITY] Error during Gemini setup: {str(setup_err)}")
                    traceback.print_exc()
                    await self.ws.close()
                    self.ws = None
                    self.connection_state = "setup_failed"
                    self._broadcast_connection_status(False)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    logger.info(f"[CONNECTIVITY] Will retry connection in {retry_delay} seconds")
                    continue
                
                # Process messages with better error handling
                try:
                    await asyncio.gather(
                        self._process_outgoing_queue(),
                        self._process_incoming_messages()
                    )
                except websockets.exceptions.ConnectionClosed as closed_err:
                    logger.warning(f"[CONNECTIVITY] Gemini WebSocket connection closed with code {closed_err.code}: {closed_err.reason}")
                    self.connection_state = "closed"
                except Exception as process_err:
                    logger.error(f"[CONNECTIVITY] Error processing messages: {str(process_err)}")
                    self.connection_state = "error"
                    traceback.print_exc()
                
            except Exception as e:
                logger.error(f"[CONNECTIVITY] Unexpected error in Gemini connection: {str(e)}")
                self.connection_state = "error"
                traceback.print_exc()
                
            finally:
                # Clear the connection in all cases
                with self.ws_lock:
                    if self.ws:
                        try:
                            logger.info("[CONNECTIVITY] Closing WebSocket connection")
                            await self.ws.close()
                        except:
                            logger.warning("[CONNECTIVITY] Error when closing WebSocket connection")
                        self.ws = None
                
                # Notify of disconnection
                self.connection_state = "disconnected"
                self._broadcast_connection_status(False)
                
                # Wait before reconnecting
                logger.info(f"[CONNECTIVITY] Will attempt reconnection in {retry_delay} seconds")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
                
    async def _process_outgoing_queue(self):
        """Process messages from the outgoing queue and send to Gemini"""
        while self.running and self.ws:
            try:
                # Check if there are messages to send
                if not self.outgoing_queue.empty():
                    message = self.outgoing_queue.get()
                    
                    # Log message details for debugging
                    if isinstance(message, dict):
                        msg_type = message.get('type', 'client_content')
                        
                        # Log more details about the message content
                        if 'clientContent' in message:
                            turns = message.get('clientContent', {}).get('turns', [])
                            if turns and len(turns) > 0:
                                text_parts = [part.get('text', '') for turn in turns for part in turn.get('parts', []) if 'text' in part]
                                
                    
                    # Send the message
                    serialized = json.dumps(message)
                    await self.ws.send(serialized)
                
                # Brief pause to prevent high CPU usage
                await asyncio.sleep(0.01)
            
            except Exception as e:
                logger.error(f"Error processing outgoing message: {str(e)}")
                traceback.print_exc()
                await asyncio.sleep(1)
    
    async def _process_incoming_messages(self):
        """Process incoming messages from Gemini API"""
        current_response = ""  # Buffer to accumulate text chunks
        turn_in_progress = False
        
        
        while self.running and self.ws:
            try:
                # Receive message from Gemini
                raw_response = await self.ws.recv()
               
                # Parse JSON response
                try:
                    response = json.loads(raw_response)
                    
                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to parse JSON response: {str(json_err)}")
                    logger.debug(f"Invalid JSON: {raw_response[:100]}...")
                    continue
                
                # Check for setupComplete
                if "setupComplete" in response:
                    logger.info("Received setupComplete message")
                    continue
                    
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
                        logger.info("Generation was interrupted")
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
                            "complete": turn_complete
                        }
                        
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
                logger.warning(f"[CONNECTIVITY] Gemini WebSocket connection closed: {ws_err}")
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
        
    def process_incoming_messages(self, callback):
        """Process any incoming messages and call the provided callback"""
        # Create a module-level reference to the logger to ensure it's always available
        _logger = logging.getLogger("gemini_service")
        
        try:
            while not self.incoming_queue.empty():
                try:
                    message = self.incoming_queue.get_nowait()
                    _logger.debug(f"Processing message from queue: {message.get('type', 'unknown')}")
                    callback(message)
                except Exception as e:
                    # Use the local logger reference
                    _logger.error(f"Error processing incoming message queue: {str(e)}")
                    traceback.print_exc()
        except Exception as e:
            _logger.error(f"Error in process_incoming_messages: {str(e)}")
            traceback.print_exc()