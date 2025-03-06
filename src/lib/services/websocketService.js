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
    this.maxReconnectAttempts = 5;
    this.reconnectTimeout = null;
    this.reconnectInterval = 3000; // 3 seconds

    // Add message handlers collection
    this.messageHandlers = new Set();

    this.statusInterval = null;

    // Debug flags for troubleshooting
    this.debugMode = false; // Set to true to enable additional logging
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
    if (this.socket?.readyState === WebSocket.OPEN) {
      console.log("Already connected, skipping connection attempt");
      return;
    }

    if (this.socket?.readyState === WebSocket.CONNECTING) {
      console.log("Already connecting, skipping connection attempt");
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

        // Send an initial ping message to test the connection
        if (this.debugMode) {
          try {
            this.socket.send(
              JSON.stringify({
                type: "ping",
                timestamp: new Date().toISOString(),
              })
            );
            console.log("[DEBUG] Sent initial ping message");
          } catch (e) {
            console.error("[DEBUG] Error sending initial ping:", e);
          }
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

        // Only reconnect for specific error codes
        if (!event.wasClean && event.code !== 1000) {
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            const delay = Math.min(
              1000 * Math.pow(2, this.reconnectAttempts),
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
            console.log("Max reconnection attempts reached");
          }
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

      // Broadcast the raw message to all handlers
      this.messageHandlers.forEach((handler) => {
        handler({
          type: "debug_model_info",
          connected_clients: data.connected_clients,
          unique_clients: data.unique_clients,
          is_computing: data.is_computing,
          active_rewards: data.active_rewards,
        });
      });
    } else {
      // Handle other message types
      this.messageHandlers.forEach((handler) => handler(data));
    }
  }

  notifyStores() {
    // Update stores with new socket instance
    import("../stores/parameterStore").then((module) => {
      module.parameterStore.setSocket(this.socket);
    });
    import("../stores/rewardStore").then((module) => {
      module.rewardStore.setSocket(this.socket);
    });
  }

  disconnect() {
    this.stopStatusCheck();
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

  send(data) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      // If this is a clean_rewards message, schedule an immediate debug check
      if (data.type === "clean_rewards") {
        this.socket.send(
          JSON.stringify({
            ...data,
            timestamp: new Date().toISOString(),
          })
        );

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
        this.socket.send(
          JSON.stringify({
            ...data,
            timestamp: new Date().toISOString(),
          })
        );
      }
    } else {
      console.warn("WebSocket is not connected. Message not sent:", data);
    }
  }
}

export const websocketService = new WebSocketService();
