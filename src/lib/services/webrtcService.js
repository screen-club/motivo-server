import { writable } from "svelte/store";
import { websocketService } from "./websocketService";
import { v4 as uuidv4 } from "uuid";

// Reactive stores for WebRTC state
export const isLoading = writable(true);
export const hasStream = writable(false);
export const connectionLogs = writable([]);
export const currentQuality = writable("medium");

// Quality options
export const qualityOptions = [
  { id: "medium", label: "Standard (640×480)", recommended: true },
  { id: "high", label: "High (1280×960)" },
];

class WebRTCService {
  static instance;

  constructor() {
    if (WebRTCService.instance) {
      return WebRTCService.instance;
    }
    WebRTCService.instance = this;

    this.clientId = uuidv4(); // Unique ID for this client
    this.peerConnection = null;
    this.dataChannel = null;
    this.videoElement = null;
    this.maxLogEntries = 20;
    this._logs = [];

    // Add connection state tracking
    this.isConnecting = false;
    this.connectionAttempts = 0;
    this.maxConnectionAttempts = 3;
    this.reconnectTimeout = null;
    this.reconnectDelay = 3000; // 3 seconds between reconnection attempts

    // Initialize connection with WebSocket service
    this.messageHandler = this.handleMessage.bind(this);
    this.cleanupMessageHandler = websocketService.addMessageHandler(
      this.messageHandler
    );
  }

  // Logging functionality
  addLog(message) {
    const timestamp = new Date().toLocaleTimeString();
    this._logs = [
      { timestamp, message },
      ...this._logs.slice(0, this.maxLogEntries - 1),
    ];
    connectionLogs.set(this._logs);
    console.log(`${timestamp}: ${message}`);
  }

  // Set video element reference
  setVideoElement(element) {
    this.videoElement = element;
  }

  // Change video quality
  setVideoQuality(quality) {
    if (quality === this.getCurrentQuality()) return;

    this.addLog(`Requesting video quality change to: ${quality}`);

    // Send quality change request to server
    websocketService.send({
      type: "set_video_quality",
      quality: quality,
      client_id: this.clientId,
    });

    currentQuality.set(quality);

    // Restart WebRTC to apply changes, but with a longer delay to reduce server load
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }

    this.reconnectTimeout = setTimeout(() => {
      this.initWebRTC();
    }, 1000);
  }

  getCurrentQuality() {
    let result;
    currentQuality.subscribe((value) => {
      result = value;
    })();
    return result;
  }

  // Initialize WebRTC with simplified configuration
  async initWebRTC() {
    // Prevent multiple simultaneous connection attempts
    if (this.isConnecting) {
      this.addLog("Connection attempt already in progress, skipping");
      return;
    }

    // Limit reconnection attempts
    if (this.connectionAttempts >= this.maxConnectionAttempts) {
      this.addLog(
        `Maximum connection attempts (${this.maxConnectionAttempts}) reached, waiting for manual restart`
      );
      isLoading.set(false); // Stop showing loading indicator
      return;
    }

    this.isConnecting = true;
    this.connectionAttempts++;

    // Set a timeout to reset if connection gets stuck
    const connectionTimeout = setTimeout(() => {
      if (this.isConnecting) {
        this.addLog("Connection attempt timed out, resetting");
        this.isConnecting = false;

        // Clean up WebRTC if it exists
        if (this.peerConnection) {
          this.peerConnection.close();
          this.peerConnection = null;
        }

        // Try again if we haven't reached max attempts
        if (this.connectionAttempts < this.maxConnectionAttempts) {
          this.addLog("Attempting connection again after timeout");
          setTimeout(() => this.initWebRTC(), 1000);
        } else {
          isLoading.set(false);
        }
      }
    }, 15000); // 15 second timeout

    try {
      isLoading.set(true);
      this.addLog(
        `Starting WebRTC initialization (attempt ${this.connectionAttempts}/${this.maxConnectionAttempts})...`
      );

      // Clean up any existing connection
      if (this.peerConnection) {
        this.addLog("Closing existing peer connection");
        this.peerConnection.close();
        this.peerConnection = null;
      }

      // Create a new RTCPeerConnection with minimal configuration
      // Use empty configuration to avoid any ICE issues
      const configuration = {
        iceServers: [
          // Use Google's public STUN servers as fallback
          { urls: "stun:stun.l.google.com:19302" },
          { urls: "stun:stun1.l.google.com:19302" },

          // Use the custom COTURN server if available
          ...(import.meta.env.VITE_STUN_URL
            ? [{ urls: import.meta.env.VITE_STUN_URL }]
            : []),

          // Add specific TURN server for this project
          {
            urls: "stun:51.159.163.145:3478",
          },

          // Add TURN server for this project
          {
            urls: "turn:51.159.163.145:3478",
            username: "admin",
            credential: "password",
          },

          // Add TURN over TCP for this project (helps with strict firewalls)
          {
            urls: "turn:51.159.163.145:3478?transport=tcp",
            username: "admin",
            credential: "password",
          },

          // Add environment variable TURN servers if available
          ...(import.meta.env.VITE_TURN_URL &&
          import.meta.env.VITE_TURN_USERNAME &&
          import.meta.env.VITE_TURN_PASSWORD
            ? [
                {
                  urls: import.meta.env.VITE_TURN_URL,
                  username: import.meta.env.VITE_TURN_USERNAME,
                  credential: import.meta.env.VITE_TURN_PASSWORD,
                },
                {
                  urls: `${import.meta.env.VITE_TURN_URL}?transport=tcp`,
                  username: import.meta.env.VITE_TURN_USERNAME,
                  credential: import.meta.env.VITE_TURN_PASSWORD,
                },
              ]
            : []),
        ],
      };

      this.addLog(
        "Creating peer connection with ICE servers: " +
          JSON.stringify(
            configuration.iceServers.map((server) => ({ urls: server.urls }))
          )
      );

      this.peerConnection = new RTCPeerConnection(configuration);

      // Set up event handlers for the connection
      this.peerConnection.ontrack = (event) => {
        this.addLog("Track received: " + event.streams?.length + " streams");
        if (event.streams && event.streams[0]) {
          if (this.videoElement) {
            this.addLog("Setting video source to received stream");
            this.videoElement.srcObject = event.streams[0];

            // Basic video setup with minimal processing
            this.videoElement
              .play()
              .catch((e) => this.addLog("Video play error: " + e.message));

            // Simple video settings
            this.videoElement.style.width = "100%";
            this.videoElement.style.imageRendering = "auto";
            this.videoElement.style.filter = "none";
            this.videoElement.style.transform = "none";

            this.videoElement.setAttribute("playsinline", "true");
            this.videoElement.setAttribute("muted", "true");

            hasStream.set(true);
            isLoading.set(false);
            this.isConnecting = false;
            this.connectionAttempts = 0; // Reset counter on successful connection
            clearTimeout(connectionTimeout); // Clear the timeout on success
          } else {
            this.addLog("Video element not available");
            this.isConnecting = false;
            clearTimeout(connectionTimeout); // Clear the timeout on failure
          }
        }
      };

      // Completely disable ICE candidate sending to prevent server errors
      this.peerConnection.onicecandidate = (event) => {
        // Do nothing - don't send any ICE candidates to the server
        // This is the simplest fix to prevent server-side errors
      };

      // Simplified connection state monitoring
      this.peerConnection.oniceconnectionstatechange = () => {
        const state = this.peerConnection.iceConnectionState;
        this.addLog(`ICE connection state: ${state}`);

        if (
          state === "disconnected" ||
          state === "failed" ||
          state === "closed"
        ) {
          hasStream.set(false);
          isLoading.set(true);
          this.isConnecting = false;
          clearTimeout(connectionTimeout); // Clear the timeout on connection state change

          // Only attempt reconnect if we haven't reached the maximum attempts
          if (this.connectionAttempts < this.maxConnectionAttempts) {
            this.addLog(
              `Connection ${state}, will retry in ${
                this.reconnectDelay / 1000
              }s`
            );

            if (this.reconnectTimeout) {
              clearTimeout(this.reconnectTimeout);
            }

            this.reconnectTimeout = setTimeout(() => {
              const isConnected =
                websocketService.getSocket()?.readyState === WebSocket.OPEN;
              if (isConnected) {
                this.initWebRTC();
              }
            }, this.reconnectDelay);
          } else {
            this.addLog("Maximum reconnection attempts reached");
            isLoading.set(false); // Stop showing loading indicator
          }
        } else if (state === "connected") {
          this.addLog("WebRTC connection established successfully");
          this.isConnecting = false;
          this.connectionAttempts = 0; // Reset counter on successful connection
          clearTimeout(connectionTimeout); // Clear the timeout on successful connection
        }
      };

      // Add a delay before creating the offer to give the connection time to initialize
      this.addLog("Waiting briefly before creating offer...");
      await new Promise((resolve) => setTimeout(resolve, 1000));

      // Create a simple offer with basic settings
      const offerOptions = {
        offerToReceiveVideo: true,
        offerToReceiveAudio: false,
      };

      this.addLog("Creating basic WebRTC offer");
      const offer = await this.peerConnection.createOffer(offerOptions);

      // Don't modify the SDP - this was causing errors
      // Let the browser handle the SDP formatting

      this.addLog("Setting local description");
      await this.peerConnection.setLocalDescription(offer);

      // Send the offer to the server
      this.addLog("Sending offer to server");
      websocketService.send({
        type: "webrtc_offer",
        sdp: offer.sdp,
        client_id: this.clientId,
      });
    } catch (error) {
      this.addLog("Error setting up WebRTC: " + error.message);
      isLoading.set(false);
      this.isConnecting = false;
      clearTimeout(connectionTimeout); // Clear the timeout on error

      // Schedule retry with increasing delay
      if (this.connectionAttempts < this.maxConnectionAttempts) {
        const retryDelay = this.reconnectDelay * this.connectionAttempts;
        this.addLog(`Will retry in ${retryDelay / 1000}s`);

        if (this.reconnectTimeout) {
          clearTimeout(this.reconnectTimeout);
        }

        this.reconnectTimeout = setTimeout(() => {
          this.initWebRTC();
        }, retryDelay);
      }
    }
  }

  async handleWebRTCAnswer(answer) {
    try {
      this.addLog("Received WebRTC answer from server");
      if (!this.peerConnection) {
        this.addLog("No peer connection available");
        return;
      }

      const rtcAnswer = new RTCSessionDescription({
        type: answer.sdpType,
        sdp: answer.sdp,
      });

      this.addLog("Setting remote description");
      await this.peerConnection.setRemoteDescription(rtcAnswer);
      this.addLog("Remote description set successfully");
    } catch (error) {
      this.addLog("Error handling WebRTC answer: " + error.message);
      this.isConnecting = false;
    }
  }

  handleMessage(data) {
    if (data.type === "webrtc_answer" && data.client_id === this.clientId) {
      this.handleWebRTCAnswer(data);
    }

    // Handle the quality change response
    if (
      data.type === "video_quality_changed" &&
      data.client_id === this.clientId
    ) {
      this.addLog(
        `Quality change to ${data.quality}: ${
          data.success ? "successful" : "failed"
        }`
      );
    }

    // Handle server errors
    if (data.type === "error" && data.client_id === this.clientId) {
      this.addLog(`Server error: ${data.message}`);
      this.isConnecting = false;
    }
  }

  handleWebSocketStateChange(isConnected) {
    if (isConnected) {
      // Reset connection attempts on new WebSocket connection
      this.connectionAttempts = 0;
      this.isConnecting = false;

      // Initialize WebRTC when WebSocket connection is ready, with a short delay
      setTimeout(() => {
        this.initWebRTC();
      }, 500);
    } else {
      isLoading.set(true);
      hasStream.set(false);
      this.isConnecting = false;

      // Clean up WebRTC
      if (this.peerConnection) {
        this.peerConnection.close();
        this.peerConnection = null;
      }

      // Clear any pending reconnect
      if (this.reconnectTimeout) {
        clearTimeout(this.reconnectTimeout);
        this.reconnectTimeout = null;
      }
    }
  }

  // Manual restart of the connection
  restartConnection() {
    this.addLog("Manually restarting WebRTC connection");
    // Reset connection attempts on manual restart
    this.connectionAttempts = 0;
    this.isConnecting = false;

    // Clear any pending reconnect
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    this.initWebRTC();
  }

  // Clean up resources
  cleanup() {
    if (this.cleanupMessageHandler) {
      this.cleanupMessageHandler();
    }

    // Clean up WebRTC
    if (this.peerConnection) {
      this.peerConnection.close();
      this.peerConnection = null;
    }

    // Clear any pending reconnect
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    this.isConnecting = false;
  }
}

// Create and export a singleton instance
export const webrtcService = new WebRTCService();
