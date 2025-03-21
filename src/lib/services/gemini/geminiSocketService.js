import { io } from "socket.io-client";
import { writable } from "svelte/store";

export const geminiConnected = writable(false);
export const geminiResponses = writable([]);

class GeminiSocketService {
  constructor() {
    this.socket = null;
    this.connected = false;
    this.messageHandlers = [];

    // Flask server with Gemini
    this.flaskUrl = import.meta.env.VITE_API_URL;
    console.log("GeminiSocketService: Flask URL", this.flaskUrl);
  }

  connect() {
    if (this.socket) {
      console.log("GeminiSocketService: Socket instance already exists");
      // Even if we have a socket, check if it's actually connected
      if (!this.socket.connected) {
        console.log(
          "GeminiSocketService: Socket exists but is disconnected. Attempting reconnect..."
        );
        this.reconnect();
      }
      return;
    }

    try {
      this.socket = io(this.flaskUrl, {
        transports: ["websocket", "polling"], // Allow polling as fallback
        reconnectionAttempts: 100,
        reconnectionDelay: 1000,
        timeout: 20000,
        autoConnect: true,
        forceNew: false, // Don't force new to allow socket.io to manage connections
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
        geminiConnected.set(data.connected);

        // Notify all handlers
        this.messageHandlers.forEach((handler) =>
          handler({ type: "gemini_connection_status", ...data })
        );
      });

      this.socket.on("gemini_response", (data) => {
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

    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.connected = false;
      geminiConnected.set(false);
    }
  }

  reconnect() {
    // First clean up existing socket if any
    if (this.socket) {
      this.socket.removeAllListeners();
      this.socket.disconnect();
      this.socket = null;
    }

    // Reset connection state
    this.connected = false;
    geminiConnected.set(false);

    // Create a new connection
    console.log("GeminiSocketService: Attempting reconnection...");
    setTimeout(() => this.connect(), 500);
  }

  isConnected() {
    return this.connected && this.socket?.connected;
  }
}

// Create singleton instance
const geminiSocketService = new GeminiSocketService();

// Auto-connect when imported
geminiSocketService.connect();

export default geminiSocketService;
