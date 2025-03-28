import { writable } from "svelte/store";

// Create a shared computing status store
export const computingStatus = writable(false);

class WebSocketService {
  static instance; // Déclarer la propriété statique

  constructor() {
    if (WebSocketService.instance) {
      return WebSocketService.instance;
    }
    WebSocketService.instance = this;

    this.socket = null;
    this.isReady = false;
    this.wsUrl = import.meta.env.VITE_WS_URL;
    this.readyStateListeners = new Set();

    // Add reconnection settings
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 1000; // Much higher limit for persistence
    this.reconnectTimeout = null;
    this.reconnectInterval = 2000; // 2 seconds for faster reconnection
    this.heartbeatInterval = null;

    // Add message handlers collection
    this.messageHandlers = new Set();

    this.statusInterval = null;

    // Debug flags for troubleshooting
    this.debugMode = false; // Set to true to enable additional logging

    // Automatically connect when service is instantiated
    setTimeout(() => this.connect(), 100);

    // Set up connection monitor to ensure we always stay connected
    setInterval(() => {
      if (!this.isReady || this.socket?.readyState !== WebSocket.OPEN) {
        console.log(
          "Connection monitor: WebSocket not connected, reconnecting"
        );
        this.connect();
      }
    }, 30000); // Check every 30 seconds
  }

  startStatusCheck() {
    // Clear any existing interval first
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
    }

    // Start new status check with shorter interval (e.g., every second)
    this.checkModelStatus();
    this.statusInterval = setInterval(() => this.checkModelStatus(), 1000);
  }

  stopStatusCheck() {
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
      this.statusInterval = null;
    }
  }

  checkModelStatus() {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: "debug_model_info",
          timestamp: new Date().toISOString(),
        })
      );
    }
  }

  connect() {
    // Even if already connected, periodically check connection state
    if (this.socket?.readyState === WebSocket.OPEN) {
      console.log("Connection active, sending keepalive ping");
      this.sendPing();
      return;
    }

    if (this.socket?.readyState === WebSocket.CONNECTING) {
      console.log("Already connecting, waiting for completion");
      return;
    }

    try {
      console.log(`Attempting to connect to ${this.wsUrl}`);

      // Add additional debugging for network connectivity
      if (this.debugMode) {
        console.log(`[DEBUG] Browser: ${navigator.userAgent}`);
        console.log(`[DEBUG] Protocol: ${window.location.protocol}`);
        console.log(`[DEBUG] Current origin: ${window.location.origin}`);

        // Check if we're using HTTPS on the frontend but WS (not WSS) for WebSockets
        if (
          window.location.protocol === "https:" &&
          this.wsUrl.startsWith("ws:")
        ) {
          console.warn(
            "[DEBUG] Security warning: Using ws:// from an https:// page. This may be blocked by the browser."
          );
        }

        // Simple connectivity test to the backend server over HTTP
        const apiUrl = import.meta.env.VITE_API_URL;
        console.log(`[DEBUG] Checking API connectivity to ${apiUrl}`);

        fetch(`${apiUrl}/api/ping`)
          .then((response) => {
            console.log(`[DEBUG] API connectivity test: ${response.status}`);
            return response.text();
          })
          .then((text) => console.log(`[DEBUG] API response: ${text}`))
          .catch((error) =>
            console.error(`[DEBUG] API connectivity error: ${error.message}`)
          );
      }

      // Try an alternative approach - If we're connecting to a remote host, try a local connection first
      // This helps in development environments
      const wsUrlObj = new URL(this.wsUrl);
      if (
        wsUrlObj.hostname !== "localhost" &&
        wsUrlObj.hostname !== "127.0.0.1"
      ) {
        console.log(
          "[DEBUG] Remote host detected, will try localhost fallback if primary connection fails"
        );
      }

      // Create WebSocket with a timeout for connection
      this.socket = new WebSocket(this.wsUrl);

      // Set a timeout to detect stalled connections
      const connectionTimeout = setTimeout(() => {
        if (this.socket && this.socket.readyState === WebSocket.CONNECTING) {
          console.error(
            `[DEBUG] WebSocket connection timed out after 10 seconds`
          );
          // Try to close and restart
          try {
            this.socket.close();
          } catch (e) {
            console.error("[DEBUG] Error closing timed-out socket:", e);
          }
          this.socket = null;

          // Try alternative connection options if we're trying to connect to a remote host
          const wsUrlObj = new URL(this.wsUrl);
          if (
            this.reconnectAttempts === 1 &&
            wsUrlObj.hostname !== "localhost" &&
            wsUrlObj.hostname !== "127.0.0.1"
          ) {
            // Try localhost as a fallback (for development)
            console.log("[DEBUG] Trying localhost fallback...");
            const port = wsUrlObj.port || "8765";
            this.wsUrl = `ws://localhost:${port}`;
            console.log(`[DEBUG] New WebSocket URL: ${this.wsUrl}`);
          } else if (this.reconnectAttempts === 2) {
            // Try with different protocol (wss:// if we were using ws://)
            if (
              this.wsUrl.startsWith("ws:") &&
              !this.wsUrl.startsWith("wss:")
            ) {
              console.log("[DEBUG] Trying secure WebSocket (WSS) instead...");
              this.wsUrl = this.wsUrl.replace("ws:", "wss:");
              console.log(`[DEBUG] New WebSocket URL: ${this.wsUrl}`);
            }
          }

          // Try an alternative approach - sometimes the port needs a second attempt
          console.log("[DEBUG] Attempting alternative connection approach...");
          this.reconnectAttempts++;

          // Wait a moment before reconnecting
          setTimeout(() => this.connect(), 1000);
        }
      }, 10000); // 10 second timeout

      this.socket.onopen = () => {
        clearTimeout(connectionTimeout);
        console.log(`Successfully connected to ${this.wsUrl}`);
        this.isReady = true;
        this.reconnectAttempts = 0;
        this.notifyReadyStateListeners();
        this.startStatusCheck();
        this.startHeartbeat();

        // Send an initial ping message to test the connection
        try {
          this.socket.send(
            JSON.stringify({
              type: "ping",
              timestamp: new Date().toISOString(),
            })
          );
          console.log("Sent initial ping message");
        } catch (e) {
          console.error("Error sending initial ping:", e);
        }

        // Process any messages that were queued during disconnection
        if (this.messageQueue.length > 0) {
          console.log(
            `Connection restored, processing ${this.messageQueue.length} queued messages`
          );
          setTimeout(() => this.processQueue(), 500); // Short delay to ensure connection is stable
        }
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (this.debugMode) {
            console.log("[DEBUG] Received message:", data.type);
          }
          this.handleMessage(data);
        } catch (error) {
          console.error(
            "Error processing WebSocket message:",
            error,
            event.data
          );
        }
      };

      this.socket.onclose = (event) => {
        clearTimeout(connectionTimeout);
        const reason = event.reason || "No reason provided";
        console.log(
          `WebSocket disconnected - Code: ${event.code}, Reason: ${reason}, Clean: ${event.wasClean}`
        );
        this.isReady = false;
        this.notifyReadyStateListeners();
        this.stopStatusCheck();
        this.stopHeartbeat();

        // Always attempt to reconnect, even for clean disconnects
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          // Use a simpler reconnect strategy with more consistent timing
          const delay = Math.min(
            this.reconnectInterval * Math.min(this.reconnectAttempts + 1, 5),
            10000
          );

          console.log(
            `Scheduling reconnect attempt ${this.reconnectAttempts + 1}/${
              this.maxReconnectAttempts
            } in ${delay}ms`
          );

          this.reconnectTimeout = setTimeout(() => {
            this.reconnectAttempts++;
            this.connect();
          }, delay);
        } else {
          console.log("Max reconnection attempts reached, will keep trying");
          // Reset counter and keep trying
          this.reconnectAttempts = 0;
          this.reconnectTimeout = setTimeout(() => {
            this.connect();
          }, 15000);
        }
      };

      this.socket.onerror = (error) => {
        console.error("WebSocket error details:", {
          url: this.wsUrl,
          readyState: this.socket?.readyState,
          error: error,
        });

        if (this.debugMode) {
          // Try alternative diagnostic approaches
          console.log("[DEBUG] Attempting network diagnostics");

          // Check if we can connect to the server on a different port
          const wsUrlObj = new URL(this.wsUrl);
          const host = wsUrlObj.hostname;

          fetch(`http://${host}:5002/api/ping`)
            .then((response) =>
              console.log(
                `[DEBUG] HTTP connectivity to port 5002: ${response.status}`
              )
            )
            .catch((err) =>
              console.error(`[DEBUG] HTTP connectivity failed: ${err.message}`)
            );
        }
      };
    } catch (error) {
      console.error("Error creating WebSocket connection:", error);
    }
  }

  handleMessage(data) {
    // Handle debug_model_info at service level
    if (data.type === "debug_model_info") {
      // Update computing status
      computingStatus.set(data.is_computing);

      this.messageHandlers.forEach((handler) => {
        try {
          handler({
            type: "debug_model_info",
            connected_clients: data.connected_clients,
            unique_clients: data.unique_clients,
            is_computing: data.is_computing,
            active_rewards: data.active_rewards,
          });
        } catch (error) {
          console.error("[DEBUG WEBSOCKET] Error in handler:", error);
        }
      });
    } else {
      this.messageHandlers.forEach((handler) => {
        try {
          handler(data);
        } catch (error) {
          console.error(
            `[DEBUG WEBSOCKET] Error in handler for ${data.type}:`,
            error
          );
        }
      });
    }
  }

  notifyStores() {
    // Update stores with new socket instance
    import("../../stores/parameterStore").then((module) => {
      module.parameterStore.setSocket(this.socket);
    });
    import("../../stores/rewardStore").then((module) => {
      module.rewardStore.setSocket(this.socket);
    });
  }

  // Heartbeat mechanism to keep connection alive
  startHeartbeat() {
    this.stopHeartbeat(); // Clear any existing interval

    this.heartbeatInterval = setInterval(() => {
      this.sendPing();

      // Also check if we need to reconnect
      if (this.socket?.readyState !== WebSocket.OPEN) {
        console.log("Heartbeat detected closed connection, reconnecting...");
        this.stopHeartbeat();
        this.connect();
      }
    }, 15000); // Send ping every 15 seconds
  }

  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  sendPing() {
    if (this.socket?.readyState === WebSocket.OPEN) {
      try {
        this.socket.send(
          JSON.stringify({
            type: "ping",
            timestamp: new Date().toISOString(),
          })
        );
      } catch (e) {
        console.error("Error sending ping:", e);
        // Connection might be broken, try reconnecting
        this.connect();
      }
    }
  }

  disconnect() {
    this.stopStatusCheck();
    this.stopHeartbeat();

    // Clear any pending reconnection attempts
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.socket) {
      this.socket.close(1000, "Intentional disconnect"); // Use 1000 for normal closure
      this.socket = null;
      this.reconnectAttempts = 0;
    }
  }

  getSocket() {
    return this.socket;
  }

  onReadyStateChange(callback) {
    this.readyStateListeners.add(callback);
    // Return cleanup function
    return () => this.readyStateListeners.delete(callback);
  }

  notifyReadyStateListeners() {
    for (const listener of this.readyStateListeners) {
      listener(this.isReady);
    }
  }

  // Add method to register message handlers
  addMessageHandler(handler) {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler); // Return cleanup function
  }

  updateReward(rewardIndex, updatedParams) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: "update_reward",
          index: rewardIndex,
          parameters: updatedParams,
          timestamp: new Date().toISOString(),
        })
      );
    }
  }

  // Message queue for unsent messages during disconnection
  messageQueue = [];
  maxQueueSize = 50; // Limit queue size to prevent memory issues

  send(data) {
    // Prepare the full message with timestamp
    const message = {
      ...data,
      timestamp: new Date().toISOString(),
    };

    if (this.socket?.readyState === WebSocket.OPEN) {
      // If this is a clean_rewards message, schedule an immediate debug check
      if (data.type === "clean_rewards") {
        this.socket.send(JSON.stringify(message));

        // Trigger immediate debug check
        setTimeout(() => {
          this.socket.send(
            JSON.stringify({
              type: "debug_model_info",
              timestamp: new Date().toISOString(),
            })
          );
        }, 100); // Small delay to ensure reset completes first
      } else {
        // Normal message sending
        console.log("SENDING MESSAGE:", message);
        this.socket.send(JSON.stringify(message));
      }

      // Process any queued messages if connection is now available
      this.processQueue();
    } else {
      // Queue the message for later delivery
      // Don't queue debug_model_info messages as they're frequent status checks
      if (data.type !== "debug_model_info") {
        this.queueMessage(message);
        console.warn(
          "WebSocket is not connected. Message queued for later delivery:",
          data
        );
      } else {
        console.warn(
          "WebSocket is not connected. Status check message not sent."
        );
      }
    }
  }

  // Make a snapshot request to the server
  makeSnapshot() {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: "make_snapshot",
          timestamp: new Date().toISOString(),
        })
      );
      return true;
    }
    return false;
  }

  queueMessage(message) {
    // Add message to queue, respecting max size
    if (this.messageQueue.length < this.maxQueueSize) {
      this.messageQueue.push(message);
    } else {
      // Remove oldest message if queue is full
      this.messageQueue.shift();
      this.messageQueue.push(message);
      console.warn("WebSocket message queue full, dropped oldest message");
    }
  }

  processQueue() {
    // Only process if socket is open and we have queued messages
    if (
      this.socket?.readyState === WebSocket.OPEN &&
      this.messageQueue.length > 0
    ) {
      console.log(`Processing ${this.messageQueue.length} queued messages`);

      // Create a copy of queue and clear the original
      const queueCopy = [...this.messageQueue];
      this.messageQueue = [];

      // Send all queued messages
      queueCopy.forEach((message) => {
        try {
          this.socket.send(JSON.stringify(message));
        } catch (error) {
          console.error("Error sending queued message:", error);
          // Re-queue on failure if it's an important message
          if (message.type !== "debug_model_info") {
            this.queueMessage(message);
          }
        }
      });
    }
  }
}

export const websocketService = new WebSocketService();
