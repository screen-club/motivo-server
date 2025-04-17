import { writable, get } from "svelte/store";
// Import the parameter store
import { parameterStore } from "../../stores/parameterStore.js";
// Import LLM stores
import {
  llmPromptStore,
  defaultPresetPromptStore,
} from "../../stores/llmInteractionStore.js";

// Create a shared computing status store
export const computingStatus = writable(false);

// Global singleton instance and connection state
const WS_STATE = {
  socket: null,
  isConnected: false,
  connectingInProgress: false,
};

/**
 * Simplified WebSocketService with strict singleton pattern
 */
class WebSocketService {
  constructor() {
    this.wsUrl = import.meta.env.VITE_WS_URL;
    this.messageHandlers = new Set();
    this.readyStateListeners = new Set();
    this.processedMessageIds = new Set();
    this.messageQueue = [];
    this.pingInterval = null;

    console.log("🌐 INITIALIZING WEBSOCKET SERVICE");

    // Don't auto-connect on instantiation - let components explicitly connect when needed
  }

  /**
   * Connect to the WebSocket server, with safeguards against multiple connections
   */
  connect() {
    // Skip if we're already connected or connecting
    if (WS_STATE.isConnected || WS_STATE.connectingInProgress) {
      console.log("WebSocket already connected or connecting, skipping");
      return;
    }

    // Set connecting state
    WS_STATE.connectingInProgress = true;
    console.log(`🔌 Connecting to WebSocket at ${this.wsUrl}`);

    try {
      // Create new WebSocket
      WS_STATE.socket = new WebSocket(this.wsUrl);

      // Handle connection open
      WS_STATE.socket.onopen = () => {
        console.log("🟢 WebSocket connection established");
        WS_STATE.isConnected = true;
        WS_STATE.connectingInProgress = false;

        // Notify listeners
        this.notifyReadyState(true);

        // Start ping interval to keep connection alive
        this.startPingInterval();

        // Send any queued messages
        this.processQueue();
      };

      // Handle connection close
      WS_STATE.socket.onclose = (event) => {
        console.log(`WebSocket closed (${event.code})`);
        WS_STATE.isConnected = false;
        WS_STATE.connectingInProgress = false;
        WS_STATE.socket = null;

        // Notify listeners
        this.notifyReadyState(false);

        // Clear ping interval
        this.stopPingInterval();

        // Auto-reconnect unless explicitly closed
        if (event.code !== 1000 || event.reason !== "Intentional disconnect") {
          setTimeout(() => this.connect(), 3000);
        }
      };

      // Handle connection error
      WS_STATE.socket.onerror = (error) => {
        console.error("WebSocket error:", error);
        WS_STATE.connectingInProgress = false;

        // Connection failure handled by onclose
      };

      // Handle messages
      WS_STATE.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type != "smpl_update") {
            console.log("🔄 Received message:", data);
          }

          // Skip duplicate messages
          if (
            data.message_id &&
            this.processedMessageIds.has(data.message_id)
          ) {
            return;
          }

          // Add to processed set
          if (data.message_id) {
            this.processedMessageIds.add(data.message_id);

            // Keep set size manageable
            if (this.processedMessageIds.size > 500) {
              const arr = Array.from(this.processedMessageIds);
              this.processedMessageIds = new Set(arr.slice(arr.length - 250));
            }
          }

          // Update computing status if present
          if (
            data.type === "debug_model_info" &&
            data.hasOwnProperty("is_computing")
          ) {
            computingStatus.set(data.is_computing);
          }

          // If it's a gemini response with environment data, update the store
          if (
            data.type === "gemini_response" &&
            typeof data.environnement === "object" &&
            data.environnement !== null
          ) {
            console.log(
              "Received environment update from Gemini:",
              data.environnement
            );
            parameterStore.updateEnvironmentParameters(data.environnement);
          }

          // Notify all message handlers
          this.messageHandlers.forEach((handler) => {
            try {
              handler(data);
            } catch (error) {
              console.error(`Error in message handler:`, error);
            }
          });
        } catch (error) {
          console.error("Error parsing WebSocket message:", error);
        }
      };
    } catch (error) {
      console.error("Error creating WebSocket:", error);
      WS_STATE.connectingInProgress = false;

      // Try reconnecting after delay
      setTimeout(() => this.connect(), 3000);
    }
  }

  /**
   * Start ping interval to keep connection alive
   */
  startPingInterval() {
    this.stopPingInterval();

    this.pingInterval = setInterval(() => {
      if (
        WS_STATE.isConnected &&
        WS_STATE.socket?.readyState === WebSocket.OPEN
      ) {
        WS_STATE.socket.send(
          JSON.stringify({
            type: "ping",
            timestamp: new Date().toISOString(),
          })
        );
      } else {
        // Connection lost, try reconnecting
        this.connect();
      }
    }, 15000); // Send ping every 15 seconds
  }

  /**
   * Stop ping interval
   */
  stopPingInterval() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  /**
   * Disconnect from the WebSocket server
   */
  disconnect() {
    this.stopPingInterval();

    if (WS_STATE.socket) {
      WS_STATE.socket.close(1000, "Intentional disconnect");
      WS_STATE.socket = null;
      WS_STATE.isConnected = false;
    }
  }

  /**
   * Send a message through the WebSocket
   */
  send(data) {
    // Add timestamp and message ID
    const message = {
      ...data,
      timestamp: new Date().toISOString(),
      message_id:
        data.message_id ||
        Date.now() + "-" + Math.random().toString(36).substring(2, 10),
    };

    // Send if connected
    if (
      WS_STATE.isConnected &&
      WS_STATE.socket?.readyState === WebSocket.OPEN
    ) {
      WS_STATE.socket.send(JSON.stringify(message));

      // Process any queued messages
      this.processQueue();
    } else if (data.type !== "debug_model_info" && data.type !== "ping") {
      // Queue important messages for later (skip frequent status messages)
      this.queueMessage(message);
    }
  }

  /**
   * Add a message to the queue for later delivery
   */
  queueMessage(message) {
    // Limit queue size
    if (this.messageQueue.length >= 50) {
      this.messageQueue.shift();
    }

    this.messageQueue.push(message);
  }

  /**
   * Process queued messages
   */
  processQueue() {
    if (!WS_STATE.isConnected || !this.messageQueue.length) {
      return;
    }

    const queueCopy = [...this.messageQueue];
    this.messageQueue = [];

    queueCopy.forEach((message) => {
      if (WS_STATE.socket?.readyState === WebSocket.OPEN) {
        WS_STATE.socket.send(JSON.stringify(message));
      } else {
        this.queueMessage(message);
      }
    });
  }

  /**
   * Register a message handler
   */
  addMessageHandler(handler) {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  /**
   * Register a ready state listener
   */
  onReadyStateChange(callback) {
    this.readyStateListeners.add(callback);

    // Call immediately with current state
    if (callback && typeof callback === "function") {
      try {
        callback(WS_STATE.isConnected);
      } catch (e) {
        console.error("Error in ready state callback:", e);
      }
    }

    // Return cleanup function
    return () => this.readyStateListeners.delete(callback);
  }

  /**
   * Notify all ready state listeners
   */
  notifyReadyState(isReady) {
    this.readyStateListeners.forEach((listener) => {
      try {
        listener(isReady);
      } catch (error) {
        console.error("Error in ready state listener:", error);
      }
    });
  }

  /**
   * Get current connection state
   */
  isConnected() {
    return WS_STATE.isConnected;
  }

  /**
   * Get socket instance (for backward compatibility)
   */
  getSocket() {
    return WS_STATE.socket;
  }

  /**
   * Update an existing reward
   */
  updateReward(rewardIndex, updatedParams) {
    this.send({
      type: "update_reward",
      index: rewardIndex,
      parameters: updatedParams,
    });
  }

  /**
   * Request a snapshot from the server
   */
  makeSnapshot() {
    this.send({
      type: "make_snapshot",
    });
    return WS_STATE.isConnected;
  }
}

// Export singleton instance
export const websocketService = new WebSocketService();
