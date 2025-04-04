import { io } from "socket.io-client";
import { writable } from "svelte/store";

export const geminiConnected = writable(false);
export const geminiResponses = writable([]);

class GeminiSocketService {
  constructor() {
    this.socket = null;
    this.connected = false;
    this.messageHandlers = [];
    this.isReconnectingFlag = false;
    this.connectionCount = 0;

    // Flask server with Gemini
    this.flaskUrl = import.meta.env.VITE_API_URL;
    console.log("GeminiSocketService: Flask URL", this.flaskUrl);
  }

  connect() {
    // Keep track of connections but don't create multiple sockets
    this.connectionCount++;

    // If we already have a socket that's connected, just return
    if (this.socket && this.socket.connected) {
      console.log(
        "GeminiSocketService: Already connected, connection count: " +
          this.connectionCount
      );
      return;
    }

    // If we have a socket that's reconnecting, don't try to create a new one
    if (this.socket && this.isReconnectingFlag) {
      console.log("GeminiSocketService: Socket is already reconnecting");
      return;
    }

    // Clean up any existing socket
    if (this.socket) {
      console.log(
        "GeminiSocketService: Cleaning up existing socket connection"
      );
      try {
        this.socket.disconnect();
      } catch (err) {
        console.error("Error disconnecting socket:", err);
      }
      this.socket = null;
    }

    console.log(
      "GeminiSocketService: Creating new socket connection to",
      this.flaskUrl
    );
    try {
      // Create a new socket with better configuration
      this.socket = io(this.flaskUrl, {
        transports: ["polling", "websocket"], // Start with polling for better compatibility
        reconnection: true,
        reconnectionAttempts: 5,
        reconnectionDelay: 1000,
        timeout: 10000,
        autoConnect: true,
        forceNew: true, // Force new connection to avoid conflicts
        path: "/socket.io", // Explicit path
      });

      this.socket.on("connect", () => {
        console.log("GeminiSocketService: Connected to Flask Socket.IO", {
          id: this.socket.id,
          transport: this.socket.io.engine.transport.name,
        });
        this.connected = true;
        geminiConnected.set(true);

        // Immediately check Gemini connection
        this.socket.emit("gemini_connect");

        // Setup periodic status check
        if (this.statusInterval) {
          clearInterval(this.statusInterval);
        }
        this.statusInterval = setInterval(() => {
          if (this.socket && this.socket.connected) {
            this.socket.emit("gemini_connect");
          }
        }, 10000); // Check every 10 seconds
      });

      this.socket.on("gemini_connection_status", (data) => {
        // Simple logging and state update
        console.log(
          "GeminiSocketService: Connection status:",
          data.connected,
          data.state
        );

        // Update connected state
        this.connected = data.connected;
        geminiConnected.set(data.connected);

        // Directly pass through all data without special handling
        this.messageHandlers.forEach((handler) =>
          handler({ type: "gemini_connection_status", ...data })
        );
      });

      this.socket.on("gemini_response", (data) => {
        console.log(
          "GeminiSocketService: Received response",
          data.complete ? "(complete)" : "(streaming)",
          data.content ? data.content.substring(0, 30) + "..." : "no content"
        );

        // Add to responses store if it has content
        if (data.content) {
          // Include image information in the response if available
          const response = {
            ...data,
            // Ensure image path and timestamp are properly passed through
            image_path: data.image_path,
            image_timestamp: data.image_timestamp,
          };

          geminiResponses.update((responses) => [...responses, response]);
        }

        // Create a custom event to broadcast to all components
        window.dispatchEvent(
          new CustomEvent("gemini-message", {
            detail: {
              type: "gemini_response",
              ...data,
            },
          })
        );

        // Notify all handlers
        this.messageHandlers.forEach((handler) => {
          try {
            handler({ type: "gemini_response", ...data });
          } catch (error) {
            console.error("[DEBUG GEMINI SOCKET] Error in handler:", error);
          }
        });
      });

      this.socket.on("disconnect", () => {
        console.log("GeminiSocketService: Disconnected from Flask Socket.IO");
        this.connected = false;
        geminiConnected.set(false);
      });

      this.socket.on("connect_error", (error) => {
        console.error("GeminiSocketService: Connection error", error);
      });
    } catch (error) {
      console.error("GeminiSocketService: Setup error", error);
    }
  }

  sendMessage(text, options = {}) {
    if (!this.socket || !this.socket.connected) {
      console.error("GeminiSocketService: Cannot send message - not connected");
      return false;
    }

    // Add support for auto-capture flag and other options
    const message = {
      text,
      add_to_existing: options.addToExisting || false,
      auto_capture: options.isAutoCapture || false, // Mark if this is an auto-capture reward
      include_image: options.includeImage !== false,
    };

    if (message.auto_capture) {
      console.log("GeminiSocketService: Sending auto-capture message");
    }

    this.socket.emit("gemini_message", message);
    return true;
  }

  addMessageHandler(handler) {
    this.messageHandlers.push(handler);
    return () => {
      this.messageHandlers = this.messageHandlers.filter((h) => h !== handler);
    };
  }

  disconnect() {
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
      this.statusInterval = null;
    }

    // Decrement connection count
    if (this.connectionCount > 0) {
      this.connectionCount--;
    }

    console.log(
      `GeminiSocketService: Disconnect called, connection count now ${this.connectionCount}`
    );

    // Only fully disconnect if no more connections are using this service
    if (this.connectionCount === 0 && this.socket) {
      console.log(
        "GeminiSocketService: No more active connections, disconnecting socket"
      );

      try {
        // Clean up all event listeners first
        this.socket.removeAllListeners();

        // Then close any connections
        this.socket.disconnect();

        // Force close the engine too
        if (this.socket.io && this.socket.io.engine) {
          this.socket.io.engine.close();
        }
      } catch (err) {
        console.error("Error during socket disconnect:", err);
      }

      // Clear references
      this.socket = null;
      this.connected = false;
      geminiConnected.set(false);
    } else {
      console.log(
        `GeminiSocketService: ${this.connectionCount} connections still active, not disconnecting socket`
      );
    }
  }

  reconnect() {
    // Prevent multiple simultaneous reconnection attempts
    if (this.isReconnectingFlag) {
      console.log("GeminiSocketService: Reconnection already in progress");
      return;
    }

    this.isReconnectingFlag = true;

    // Always clean up the existing socket to prevent issues
    if (this.socket) {
      console.log("GeminiSocketService: Cleaning up socket for reconnection");

      try {
        // Remove all listeners first
        this.socket.removeAllListeners();

        // Then close any open connections
        if (this.socket.connected) {
          this.socket.disconnect();
        }

        // Clear IO managers and engine
        if (this.socket.io) {
          try {
            this.socket.io.engine.close();
          } catch (e) {
            console.error("Error closing socket engine:", e);
          }
        }
      } catch (err) {
        console.error("Error during socket cleanup:", err);
      }

      // Null out the socket reference
      this.socket = null;
    }

    // Reset connection state
    this.connected = false;
    geminiConnected.set(false);

    // Create a new connection with a delay
    console.log("GeminiSocketService: Attempting reconnection...");
    setTimeout(() => {
      try {
        this.connect();
      } catch (e) {
        console.error("Error during reconnection:", e);
      } finally {
        this.isReconnectingFlag = false;
      }
    }, 2000);
  }

  isConnected() {
    return this.connected && this.socket?.connected;
  }

  isReconnecting() {
    return this.isReconnectingFlag;
  }

  getConnectionCount() {
    return this.connectionCount;
  }
}

// Create singleton instance
const geminiSocketService = new GeminiSocketService();

// Auto-connect when imported
geminiSocketService.connect();

export default geminiSocketService;
