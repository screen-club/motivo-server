/**
 * WebRTC service for video streaming
 * 
 * Handles connection establishment, reconnection logic, 
 * and quality configuration for WebRTC video streaming.
 */
import { v4 as uuidv4 } from "uuid";
import { isLoading, hasStream, currentQuality, ConnectionLogger } from "./connectionState.js";
import { getIceServers, CONNECTION_CONFIG, QUALITY_OPTIONS, calculateBackoff } from "./config.js";
import { websocketService } from "../websocket/index.js";

class WebRTCService {
  constructor() {
    // Singleton pattern
    if (WebRTCService.instance) {
      return WebRTCService.instance;
    }
    WebRTCService.instance = this;

    // Client identification
    this.clientId = uuidv4();
    
    // Connection objects
    this.peerConnection = null;
    this.videoElement = null;
    
    // Logging
    this.logger = new ConnectionLogger(100);
    
    // Connection state tracking
    this.isConnecting = false;
    this.connectionAttempts = 0;
    this.reconnectTimeout = null;
    this.connectionCheckInterval = null;
    
    // Initialize WebSocket handler
    this.messageHandler = this.handleWebSocketMessage.bind(this);
    this.cleanupMessageHandler = websocketService.addMessageHandler(
      this.messageHandler
    );
    
    // Initialize with default quality
    currentQuality.subscribe(quality => {
      this.quality = quality;
    });
  }
  
  /* PUBLIC API */
  
  /**
   * Set the video element to display the WebRTC stream
   */
  setVideoElement(element) {
    this.videoElement = element;
    this.logger.log(`Video element ${element ? 'set' : 'cleared'}`);
  }
  
  /**
   * Change the video quality
   */
  setVideoQuality(quality) {
    if (quality === this.quality) return;
    
    this.logger.log(`Changing video quality to ${quality}`);
    
    // Update quality store
    currentQuality.set(quality);
    
    // Send quality change request
    websocketService.send({
      type: "set_video_quality",
      quality: quality,
      client_id: this.clientId
    });
    
    // Restart connection after a short delay
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }
    
    this.reconnectTimeout = setTimeout(() => {
      this.initWebRTC();
    }, 1000);
  }
  
  /**
   * Handle WebSocket state changes
   */
  handleWebSocketStateChange(isConnected) {
    if (isConnected) {
      this.logger.log("WebSocket connected, resetting connection state");
      // Reset connection state on new WebSocket connection
      this.connectionAttempts = 0;
      this.isConnecting = false;
      
      // Initialize WebRTC with a short delay
      setTimeout(() => this.initWebRTC(), 500);
    } else {
      this.logger.warn("WebSocket disconnected, cleaning up WebRTC");
      isLoading.set(true);
      hasStream.set(false);
      this.isConnecting = false;
      
      // Clean up WebRTC
      this.closeConnection();
      
      // Clear scheduled tasks
      this.clearTimeouts();
    }
  }
  
  /**
   * Manually restart the WebRTC connection
   */
  restartConnection() {
    this.logger.log("Manually restarting WebRTC connection");
    
    // Reset connection state
    this.connectionAttempts = 0;
    this.isConnecting = false;
    
    // Clean up any existing connection
    this.closeConnection();
    this.clearTimeouts();
    
    // Start fresh
    this.initWebRTC();
  }
  
  /**
   * Clean up all resources
   */
  cleanup() {
    this.logger.log("Cleaning up WebRTC service");
    
    // Remove WebSocket handler
    if (this.cleanupMessageHandler) {
      this.cleanupMessageHandler();
    }
    
    // Close connection
    this.closeConnection();
    
    // Clear scheduled tasks
    this.clearTimeouts();
    
    this.isConnecting = false;
  }
  
  /**
   * Get a readable client identifier
   */
  getShortClientId() {
    return this.clientId.substring(0, 8);
  }
  
  /* INTERNAL METHODS */
  
  /**
   * Initialize WebRTC connection
   */
  async initWebRTC() {
    // Guard against multiple simultaneous connection attempts
    if (this.isConnecting) {
      this.logger.log("Connection already in progress, skipping");
      return;
    }
    
    // Check max reconnection attempts
    if (this.connectionAttempts >= CONNECTION_CONFIG.maxAttempts) {
      this.logger.warn(`Maximum connection attempts (${CONNECTION_CONFIG.maxAttempts}) reached`);
      isLoading.set(false);
      return;
    }
    
    // Start connection process
    this.isConnecting = true;
    this.connectionAttempts++;
    isLoading.set(true);
    
    // Set up timeout in case connection gets stuck
    const timeoutId = setTimeout(() => {
      if (this.isConnecting) {
        this.logger.warn("Connection attempt timed out");
        this.handleConnectionFailure();
      }
    }, CONNECTION_CONFIG.offerTimeout);
    
    try {
      this.logger.log(`Starting WebRTC connection (attempt ${this.connectionAttempts}/${CONNECTION_CONFIG.maxAttempts})`);
      
      // Close any existing connection
      this.closeConnection();
      
      // Create a new RTCPeerConnection with ICE configuration
      this.logger.log("Creating peer connection");
      this.peerConnection = new RTCPeerConnection({
        iceServers: getIceServers()
      });
      
      // Set up event handlers
      this.setupPeerConnectionEvents();
      
      // Create and send offer
      await this.createAndSendOffer();
      
      // Clear timeout as we've successfully sent the offer
      clearTimeout(timeoutId);
      
      // Start connection health check
      this.startConnectionHealthCheck();
      
    } catch (error) {
      this.logger.error("Error setting up WebRTC", error);
      clearTimeout(timeoutId);
      this.handleConnectionFailure();
    }
  }
  
  /**
   * Set up event handlers for the peer connection
   */
  setupPeerConnectionEvents() {
    // Handle incoming media tracks
    this.peerConnection.ontrack = (event) => {
      this.logger.log(`Track received with ${event.streams?.length || 0} streams`);
      
      if (event.streams && event.streams[0]) {
        if (this.videoElement) {
          this.logger.log("Setting video source to received stream");
          this.videoElement.srcObject = event.streams[0];
          
          // Play video with error handling
          this.videoElement.play()
            .catch(e => this.logger.error("Video play error", e));
          
          hasStream.set(true);
          isLoading.set(false);
          this.isConnecting = false;
          this.connectionAttempts = 0; // Reset counter on success
        } else {
          this.logger.warn("Video element not available");
          this.isConnecting = false;
        }
      }
    };
    
    // Handle ICE connection state changes
    this.peerConnection.oniceconnectionstatechange = () => {
      const state = this.peerConnection?.iceConnectionState;
      this.logger.log(`ICE connection state: ${state}`);
      
      if (state === "connected" || state === "completed") {
        this.logger.log("WebRTC connection established successfully");
        hasStream.set(true);
        isLoading.set(false);
        this.isConnecting = false;
        this.connectionAttempts = 0; // Reset counter on success
      } 
      else if (state === "disconnected" || state === "failed" || state === "closed") {
        this.logger.warn(`ICE connection ${state}`);
        hasStream.set(false);
        this.handleConnectionFailure();
      }
    };
    
    // ICE candidate handling - send candidates to the server
    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        // Send ICE candidate to server 
        websocketService.send({
          type: "webrtc_ice",
          candidate: {
            sdpMid: event.candidate.sdpMid,
            sdpMLineIndex: event.candidate.sdpMLineIndex,
            candidate: event.candidate.candidate,
            type: event.candidate.type,
            foundation: event.candidate.foundation,
            protocol: event.candidate.protocol,
            ip: event.candidate.ip,
            port: event.candidate.port,
            priority: event.candidate.priority,
            component: event.candidate.component || 0
          },
          client_id: this.clientId
        });
        this.logger.log("Sent ICE candidate to server");
      }
    };
    
    // Connection state monitoring
    this.peerConnection.onconnectionstatechange = () => {
      const state = this.peerConnection?.connectionState;
      this.logger.log(`Connection state: ${state}`);
      
      if (state === "failed" || state === "closed") {
        this.logger.warn(`Connection state ${state}`);
        hasStream.set(false);
        this.handleConnectionFailure();
      }
    };
  }
  
  /**
   * Create and send WebRTC offer to server
   */
  async createAndSendOffer() {
    // Add a short delay to give the connection time to initialize
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // Create offer with video only
    this.logger.log("Creating WebRTC offer");
    const offer = await this.peerConnection.createOffer({
      offerToReceiveVideo: true,
      offerToReceiveAudio: false
    });
    
    // Set local description
    this.logger.log("Setting local description");
    await this.peerConnection.setLocalDescription(offer);
    
    // Send offer to server
    this.logger.log("Sending offer to server");
    websocketService.send({
      type: "webrtc_offer",
      sdp: offer.sdp,
      client_id: this.clientId
    });
  }
  
  /**
   * Handle incoming WebRTC answer from server
   */
  async handleWebRTCAnswer(answer) {
    try {
      this.logger.log("Received WebRTC answer from server");
      
      if (!this.peerConnection) {
        this.logger.warn("No peer connection available");
        return;
      }
      
      // Create RTCSessionDescription from answer
      const rtcAnswer = new RTCSessionDescription({
        type: answer.sdpType,
        sdp: answer.sdp
      });
      
      // Set remote description
      this.logger.log("Setting remote description");
      await this.peerConnection.setRemoteDescription(rtcAnswer);
      this.logger.log("Remote description set successfully");
      
    } catch (error) {
      this.logger.error("Error handling WebRTC answer", error);
      this.isConnecting = false;
      this.handleConnectionFailure();
    }
  }
  
  /**
   * Process messages from WebSocket
   */
  handleWebSocketMessage(data) {
    // Only process messages intended for this client
    if (data.client_id && data.client_id !== this.clientId) {
      return;
    }
    
    // Handle WebRTC answer
    if (data.type === "webrtc_answer" && data.client_id === this.clientId) {
      this.handleWebRTCAnswer(data);
    }
    
    // Handle quality change response
    if (data.type === "video_quality_changed" && data.client_id === this.clientId) {
      this.logger.log(`Quality change to ${data.quality}: ${data.success ? "successful" : "failed"}`);
    }
    
    // Handle server errors
    if (data.type === "error" && data.client_id === this.clientId) {
      this.logger.error(`Server error: ${data.message}`);
      this.isConnecting = false;
    }
  }
  
  /**
   * Handle connection failure with exponential backoff
   */
  handleConnectionFailure() {
    // Mark connection as failed
    this.isConnecting = false;
    hasStream.set(false);
    
    // Only retry if we haven't reached max attempts
    if (this.connectionAttempts < CONNECTION_CONFIG.maxAttempts) {
      // Calculate backoff time
      const delay = calculateBackoff(
        this.connectionAttempts,
        CONNECTION_CONFIG.baseDelay,
        CONNECTION_CONFIG.maxDelay
      );
      
      this.logger.log(`Connection failed, retrying in ${Math.round(delay/1000)}s (attempt ${this.connectionAttempts}/${CONNECTION_CONFIG.maxAttempts})`);
      
      // Clear any existing timeout
      if (this.reconnectTimeout) {
        clearTimeout(this.reconnectTimeout);
      }
      
      // Schedule reconnection
      this.reconnectTimeout = setTimeout(() => {
        // Only reconnect if WebSocket is still open
        if (websocketService.getSocket()?.readyState === WebSocket.OPEN) {
          this.initWebRTC();
        } else {
          this.logger.warn("WebSocket closed, cannot reconnect WebRTC");
          isLoading.set(false);
        }
      }, delay);
    } else {
      this.logger.warn("Maximum reconnection attempts reached");
      isLoading.set(false);
    }
  }
  
  /**
   * Start periodic connection health check
   */
  startConnectionHealthCheck() {
    // Clear any existing interval
    if (this.connectionCheckInterval) {
      clearInterval(this.connectionCheckInterval);
    }
    
    // Set up new interval
    this.connectionCheckInterval = setInterval(() => {
      if (!this.peerConnection) return;
      
      const connectionState = this.peerConnection.connectionState;
      const iceState = this.peerConnection.iceConnectionState;
      
      // Check for problematic states
      if (
        connectionState === "disconnected" || 
        connectionState === "failed" ||
        iceState === "disconnected" ||
        iceState === "failed"
      ) {
        this.logger.warn(`Connection check failed: conn=${connectionState}, ice=${iceState}`);
        this.handleConnectionFailure();
      }
    }, CONNECTION_CONFIG.connectionCheckInterval);
  }
  
  /**
   * Close WebRTC connection
   */
  closeConnection() {
    if (this.peerConnection) {
      this.logger.log("Closing peer connection");
      this.peerConnection.close();
      this.peerConnection = null;
    }
    
    if (this.videoElement) {
      // Stop tracks on video stream
      const stream = this.videoElement.srcObject;
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
        this.videoElement.srcObject = null;
      }
    }
  }
  
  /**
   * Clear all timeouts and intervals
   */
  clearTimeouts() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    if (this.connectionCheckInterval) {
      clearInterval(this.connectionCheckInterval);
      this.connectionCheckInterval = null;
    }
  }
}

// Create and export a singleton instance
export const webrtcService = new WebRTCService();