/**
 * WebRTC service for video streaming
 * 
 * A simplified implementation using standard Web APIs for maximum browser compatibility.
 */
import { v4 as uuidv4 } from "uuid";
import {
  isLoading,
  hasStream,
  currentQuality,
  ConnectionLogger,
} from "./connectionState.js";
import { 
  getIceServers, 
  CONNECTION_CONFIG,
  calculateBackoff
} from "./config.js";
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

    // Connection state tracking
    this.logger = new ConnectionLogger(100);
    this.isConnecting = false;
    this.connectionAttempts = 0;
    this.reconnectTimeout = null;
    this.healthCheckInterval = null;
    this.stats = {
      framesReceived: 0,
      framesDecoded: 0,
      packetsLost: 0,
      bytesReceived: 0,
      lastStatsTime: 0
    };

    // Subscribe to quality changes
    currentQuality.subscribe((quality) => {
      this.quality = quality;
    });

    // Register WebSocket message handler
    this.messageHandler = this.handleWebSocketMessage.bind(this);
    this.cleanupMessageHandler = websocketService.addMessageHandler(
      this.messageHandler
    );

    this.logger.log("WebRTC service initialized");
  }

  /**
   * Set the video element that will display the WebRTC stream
   */
  setVideoElement(element) {
    this.videoElement = element;
    this.logger.log(`Video element ${element ? "set" : "cleared"}`);
  }

  /**
   * Change the video stream quality
   */
  setVideoQuality(quality) {
    if (quality === this.quality) return;

    this.logger.log(`Changing video quality to ${quality}`);
    
    // Update quality store
    currentQuality.set(quality);

    // Send quality change request to server
    websocketService.send({
      type: "set_video_quality",
      quality: quality,
      client_id: this.clientId,
    });

    // Restart connection to apply new quality
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }

    this.reconnectTimeout = setTimeout(() => {
      this.restartConnection();
    }, 1000);
  }

  /**
   * Handle WebSocket connection state changes
   */
  handleWebSocketStateChange(isConnected) {
    if (isConnected) {
      this.logger.log("WebSocket connected, initializing WebRTC");
      
      // Reset connection state
      this.connectionAttempts = 0;
      this.isConnecting = false;

      // Initialize WebRTC with a short delay
      setTimeout(() => {
        if (websocketService.isConnected()) {
          this.initWebRTC();
        }
      }, 500);
    } else {
      this.logger.log("WebSocket disconnected, cleaning up WebRTC");
      
      // Update UI state
      isLoading.set(false);
      hasStream.set(false);
      
      // Clean up resources
      this.cleanupConnection();
    }
  }

  /**
   * Restart the WebRTC connection
   */
  restartConnection() {
    this.logger.log("Restarting WebRTC connection");
    
    // Reset state
    this.connectionAttempts = 0;
    this.isConnecting = false;
    
    // Clean up existing connection
    this.cleanupConnection();
    
    // Start new connection
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
      this.cleanupMessageHandler = null;
    }
    
    // Clean up connection
    this.cleanupConnection();
  }

  /**
   * Initialize WebRTC connection
   */
  async initWebRTC() {
    // Prevent multiple simultaneous connection attempts
    if (this.isConnecting) {
      this.logger.log("Connection already in progress");
      return;
    }
    
    // Check max reconnection attempts
    if (this.connectionAttempts >= CONNECTION_CONFIG.maxAttempts) {
      this.logger.log(`Maximum reconnection attempts (${CONNECTION_CONFIG.maxAttempts}) reached`);
      isLoading.set(false);
      return;
    }
    
    // Start connection process
    this.isConnecting = true;
    this.connectionAttempts++;
    isLoading.set(true);
    
    this.logger.log(`Starting WebRTC connection (attempt ${this.connectionAttempts}/${CONNECTION_CONFIG.maxAttempts})`);
    
    // Set connection timeout
    const connectionTimeout = setTimeout(() => {
      if (this.isConnecting) {
        this.logger.log("Connection attempt timed out");
        this.handleConnectionFailure();
      }
    }, CONNECTION_CONFIG.offerTimeout);
    
    try {
      // Close any existing connection
      this.cleanupPeerConnection();
      
      // Create new peer connection with ICE servers
      this.peerConnection = new RTCPeerConnection({
        iceServers: getIceServers(),
        iceCandidatePoolSize: 10,  // Pre-generate ICE candidates
        bundlePolicy: "max-bundle", // Bundle media streams
        rtcpMuxPolicy: "require"    // Multiplex RTCP
      });
      
      // Set up event handlers
      this.setupPeerConnectionEvents();
      
      // Create and send offer
      await this.createAndSendOffer();
      
      // Clear timeout since we've made progress
      clearTimeout(connectionTimeout);
      
      // Start health check
      this.startHealthCheck();
      
    } catch (error) {
      this.logger.log(`Error setting up WebRTC: ${error.message}`);
      clearTimeout(connectionTimeout);
      this.handleConnectionFailure();
    }
  }
  
  /**
   * Set up event handlers for peer connection
   */
  setupPeerConnectionEvents() {
    // Track event - when remote track is received
    this.peerConnection.ontrack = (event) => {
      this.logger.log(`Track received: ${event.track.kind}`);
      
      if (event.streams && event.streams[0] && this.videoElement) {
        this.logger.log("Attaching stream to video element");
        
        // Attach stream to video element
        this.videoElement.srcObject = event.streams[0];
        
        // Play video when ready
        const playVideo = () => {
          this.videoElement.play()
            .then(() => {
              this.logger.log("Video playback started");
              hasStream.set(true);
              isLoading.set(false);
              this.isConnecting = false;
              this.connectionAttempts = 0; // Reset on success
            })
            .catch(e => {
              // Auto-play might be blocked
              if (e.name === "NotAllowedError") {
                this.logger.log("Autoplay blocked, trying with muted");
                this.videoElement.muted = true;
                return this.videoElement.play();
              }
              throw e;
            })
            .catch(e => {
              this.logger.log(`Video playback failed: ${e.message}`);
              this.isConnecting = false;
            });
        };
        
        if (this.videoElement.readyState >= 2) { // HAVE_CURRENT_DATA or higher
          playVideo();
        } else {
          this.videoElement.addEventListener('loadeddata', playVideo, { once: true });
        }
      } else {
        this.logger.log("Video element not available");
        this.isConnecting = false;
      }
    };
    
    // ICE connection state changes
    this.peerConnection.oniceconnectionstatechange = () => {
      const state = this.peerConnection?.iceConnectionState;
      this.logger.log(`ICE connection state: ${state}`);
      
      if (state === "connected" || state === "completed") {
        // Connection successful
        this.logger.log("WebRTC connection established");
        hasStream.set(true);
        isLoading.set(false);
        this.isConnecting = false;
        this.connectionAttempts = 0;
      } else if (state === "failed") {
        // Connection failed
        this.logger.log("ICE connection failed");
        hasStream.set(false);
        this.handleConnectionFailure();
      } else if (state === "disconnected") {
        // Temporary disconnection - wait before handling as failure
        this.logger.log("ICE connection disconnected, waiting to see if it recovers");
        setTimeout(() => {
          if (this.peerConnection && this.peerConnection.iceConnectionState === "disconnected") {
            this.logger.log("ICE connection still disconnected, handling as failure");
            hasStream.set(false);
            this.handleConnectionFailure();
          }
        }, 5000);
      }
    };
    
    // ICE candidate events
    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        // Send candidate to server
        websocketService.send({
          type: "webrtc_ice",
          candidate: {
            sdpMid: event.candidate.sdpMid,
            sdpMLineIndex: event.candidate.sdpMLineIndex,
            candidate: event.candidate.candidate
          },
          client_id: this.clientId
        });
        
        this.logger.log("ICE candidate sent to server");
      } else {
        this.logger.log("End of ICE candidates");
      }
    };
    
    // Connection state changes
    this.peerConnection.onconnectionstatechange = () => {
      const state = this.peerConnection?.connectionState;
      this.logger.log(`Connection state: ${state}`);
      
      if (state === "connected") {
        this.logger.log("WebRTC connected");
        hasStream.set(true);
        isLoading.set(false);
        this.isConnecting = false;
        this.connectionAttempts = 0;
      } else if (state === "failed" || state === "closed") {
        this.logger.log(`Connection state ${state}, handling as failure`);
        hasStream.set(false);
        this.handleConnectionFailure();
      }
    };
  }
  
  /**
   * Create and send WebRTC offer to server
   */
  async createAndSendOffer() {
    this.logger.log("Creating WebRTC offer");
    
    try {
      // Create offer with video only
      const offer = await this.peerConnection.createOffer({
        offerToReceiveVideo: true,
        offerToReceiveAudio: false
      });
      
      // Set as local description
      this.logger.log("Setting local description");
      await this.peerConnection.setLocalDescription(offer);
      
      // Send offer to server
      this.logger.log("Sending offer to server");
      websocketService.send({
        type: "webrtc_offer",
        sdp: offer.sdp,
        client_id: this.clientId
      });
      
      return true;
    } catch (error) {
      this.logger.log(`Error creating offer: ${error.message}`);
      return false;
    }
  }
  
  /**
   * Handle WebRTC answer from server
   */
  async handleWebRTCAnswer(answer) {
    try {
      this.logger.log("Received WebRTC answer from server");
      
      if (!this.peerConnection) {
        this.logger.log("No peer connection available");
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
      this.logger.log(`Error handling WebRTC answer: ${error.message}`);
      this.isConnecting = false;
      this.handleConnectionFailure();
    }
  }
  
  /**
   * Process WebSocket messages
   */
  handleWebSocketMessage(data) {
    // Only process messages for this client
    if (data.client_id && data.client_id !== this.clientId) {
      return;
    }
    
    // Handle different message types
    if (data.type === "webrtc_answer" && data.client_id === this.clientId) {
      this.handleWebRTCAnswer(data);
    } else if (data.type === "video_quality_changed" && data.client_id === this.clientId) {
      this.logger.log(`Quality change to ${data.quality}: ${data.success ? "successful" : "failed"}`);
    } else if (data.type === "error" && data.client_id === this.clientId) {
      this.logger.log(`Server error: ${data.message}`);
      this.isConnecting = false;
    }
  }
  
  /**
   * Handle connection failure with improved reconnection logic
   */
  handleConnectionFailure() {
    // Mark connection as failed
    this.isConnecting = false;
    hasStream.set(false);
    
    // Only show loading for initial attempts to reduce UI flashing
    if (this.connectionAttempts > 3) {
      isLoading.set(false);
    }
    
    // Check if max attempts reached
    if (this.connectionAttempts >= CONNECTION_CONFIG.maxAttempts) {
      this.logger.log(`Max reconnection attempts (${CONNECTION_CONFIG.maxAttempts}) reached`);
      isLoading.set(false);
      
      // After reaching max attempts, set up a slower retry cycle
      // This ensures we eventually reconnect even after many failures
      if (this.reconnectTimeout) {
        clearTimeout(this.reconnectTimeout);
      }
      
      this.reconnectTimeout = setTimeout(() => {
        this.logger.log("Resetting connection retry counter and attempting reconnection");
        this.connectionAttempts = 0;
        if (websocketService.isConnected()) {
          this.initWebRTC();
        }
      }, 30000); // 30 second reset timer
      
      return;
    }
    
    // Calculate backoff delay with jitter
    const delay = calculateBackoff(
      this.connectionAttempts,
      CONNECTION_CONFIG.baseDelay,
      CONNECTION_CONFIG.maxDelay
    );
    
    this.logger.log(`Connection failed, retrying in ${Math.round(delay / 1000)}s (attempt ${this.connectionAttempts + 1}/${CONNECTION_CONFIG.maxAttempts})`);
    
    // Clear any existing timeout
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }
    
    // Schedule reconnection
    this.reconnectTimeout = setTimeout(() => {
      if (websocketService.isConnected()) {
        // Force clean up of any existing connection first
        this.cleanupConnection();
        // Then initialize a new connection
        this.initWebRTC();
      } else {
        this.logger.log("WebSocket not connected, skipping reconnection");
        this.connectionAttempts++;
        this.handleConnectionFailure();
      }
    }, delay);
  }
  
  /**
   * Start enhanced periodic health check
   */
  startHealthCheck() {
    // Clear any existing interval
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
    }
    
    this.stats.lastStatsTime = Date.now();
    this.stats.lastGoodFrameTime = Date.now();
    this.stats.consecutiveLowFrameRates = 0;
    
    // Set up new interval with shorter check time
    this.healthCheckInterval = setInterval(async () => {
      if (!this.peerConnection || this.isConnecting) {
        return;
      }
      
      try {
        // Get RTCStats
        const stats = await this.peerConnection.getStats();
        const now = Date.now();
        
        // Process video stats
        let receivedFrames = 0;
        let decodedFrames = 0;
        let packetsLost = 0;
        let bytesReceived = 0;
        let framesDropped = 0;
        let jitter = 0;
        let streamHealth = "good";
        
        stats.forEach(stat => {
          if (stat.type === 'inbound-rtp' && stat.kind === 'video') {
            receivedFrames = stat.framesReceived || 0;
            decodedFrames = stat.framesDecoded || 0;
            packetsLost = stat.packetsLost || 0;
            bytesReceived = stat.bytesReceived || 0;
            framesDropped = stat.framesDropped || 0;
            jitter = stat.jitter || 0;
            
            // Check for stalled or degraded stream
            const timeDelta = (now - this.stats.lastStatsTime) / 1000;
            const frameRate = (decodedFrames - this.stats.framesDecoded) / timeDelta;
            const packetLossRate = packetsLost > this.stats.packetsLost ? 
                                  (packetsLost - this.stats.packetsLost) / 
                                  ((bytesReceived - this.stats.bytesReceived) / 1500) : 0;
            
            // Evaluate stream health
            if (frameRate < 1 && timeDelta > 2) {
              streamHealth = "stalled";
              this.stats.consecutiveLowFrameRates++;
            } else if (frameRate < 10 || packetLossRate > 0.05 || jitter > 0.1) {
              streamHealth = "degraded";
              this.stats.consecutiveLowFrameRates++;
            } else {
              streamHealth = "good";
              this.stats.consecutiveLowFrameRates = 0;
              this.stats.lastGoodFrameTime = now;
            }
            
            // Log stats periodically or on health change
            if (now % 5000 < 1000 || this.stats.lastStreamHealth !== streamHealth) { 
              this.logger.log(
                `Stream health: ${streamHealth}, ${Math.round(frameRate)} fps, ` +
                `bitrate: ${Math.round((bytesReceived - this.stats.bytesReceived) * 8 / timeDelta / 1000)} kbps, ` +
                `packet loss: ${(packetLossRate * 100).toFixed(1)}%, jitter: ${jitter.toFixed(3)}`
              );
              this.stats.lastStreamHealth = streamHealth;
            }
            
            // Take action based on stream health
            if (streamHealth === "stalled") {
              const stalledTime = (now - this.stats.lastGoodFrameTime) / 1000;
              if (stalledTime > 3) { // Stalled for 3+ seconds
                this.logger.log(`Stream stalled for ${stalledTime.toFixed(1)}s, restarting connection`);
                this.restartConnection();
                return;
              }
            } else if (streamHealth === "degraded" && this.stats.consecutiveLowFrameRates >= 4) {
              // Multiple consecutive degraded checks - restart connection
              this.logger.log("Stream consistently degraded, restarting connection");
              this.restartConnection();
              return;
            }
            
            // Update stored stats
            this.stats.framesReceived = receivedFrames;
            this.stats.framesDecoded = decodedFrames;
            this.stats.packetsLost = packetsLost;
            this.stats.bytesReceived = bytesReceived;
            this.stats.lastStatsTime = now;
          }
        });
        
        // Check connection states
        const connState = this.peerConnection.connectionState;
        const iceState = this.peerConnection.iceConnectionState;
        
        // React to problematic states
        if (connState === 'disconnected' || connState === 'failed' || 
            iceState === 'disconnected' || iceState === 'failed') {
          this.logger.log(`Problematic connection state detected: conn=${connState}, ice=${iceState}`);
          this.handleConnectionFailure();
        }
        
        // Periodic ICE restart - helps refresh connections that are technically 
        // connected but performing poorly
        const connectionAge = (now - this.stats.lastGoodRestartTime) / 1000;
        if (connState === 'connected' && connectionAge > 300) { // 5 minutes
          this.logger.log("Performing preventive ICE restart");
          try {
            if (this.peerConnection && this.peerConnection.restartIce) {
              this.peerConnection.restartIce();
              this.stats.lastGoodRestartTime = now;
            }
          } catch (e) {
            this.logger.log(`Error during preventive ICE restart: ${e.message}`);
          }
        }
        
      } catch (error) {
        this.logger.log(`Error in health check: ${error.message}`);
      }
    }, 2500); // Check every 2.5 seconds for faster response to problems
    
    // Initialize restart time
    this.stats.lastGoodRestartTime = Date.now();
    
    this.logger.log("Started enhanced health check");
  }
  
  /**
   * Clean up peer connection
   */
  cleanupPeerConnection() {
    if (this.peerConnection) {
      this.logger.log("Closing peer connection");
      
      // Close connection
      this.peerConnection.close();
      this.peerConnection = null;
    }
    
    // Stop video tracks
    if (this.videoElement && this.videoElement.srcObject) {
      this.videoElement.srcObject.getTracks().forEach(track => track.stop());
      this.videoElement.srcObject = null;
    }
  }
  
  /**
   * Clean up all connection resources
   */
  cleanupConnection() {
    // Clean up peer connection
    this.cleanupPeerConnection();
    
    // Clear timeouts and intervals
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }
    
    // Reset state
    this.isConnecting = false;
  }
  
  /**
   * Get a shortened client ID for logging
   */
  getShortClientId() {
    return this.clientId.substring(0, 8);
  }
}

// Export singleton instance
export const webrtcService = new WebRTCService();