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
    this.flaskUrl = "http://localhost:5002";
    console.log("GeminiSocketService: Will connect to Flask at", this.flaskUrl);
  }

  connect() {
    if (this.socket) {
      console.log("GeminiSocketService: Socket instance already exists");
      return;
    }

    try {
      console.log("GeminiSocketService: Connecting to Flask Socket.IO");

      this.socket = io(this.flaskUrl, {
        transports: ["websocket"],
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        timeout: 20000,
      });

      this.socket.on("connect", () => {
        console.log("GeminiSocketService: Connected to Flask Socket.IO", {
          id: this.socket.id,
        });
        this.connected = true;
        geminiConnected.set(true);

        // Immediately check Gemini connection
        this.socket.emit("gemini_connect");
      });

      this.socket.on("gemini_connection_status", (data) => {
        console.log("GeminiSocketService: Received connection status", data);
        geminiConnected.set(data.connected);

        // Notify all handlers
        this.messageHandlers.forEach((handler) =>
          handler({ type: "gemini_connection_status", ...data })
        );
      });

      this.socket.on("gemini_response", (data) => {
        console.log("GeminiSocketService: Received response", data);

        // Add to responses store if it has content
        if (data.content) {
          geminiResponses.update((responses) => [...responses, data]);
        }

        // Notify all handlers
        this.messageHandlers.forEach((handler) =>
          handler({ type: "gemini_response", ...data })
        );
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

  sendMessage(text) {
    if (!this.socket || !this.socket.connected) {
      console.error("GeminiSocketService: Cannot send message - not connected");
      return false;
    }

    console.log("GeminiSocketService: Sending message", text);
    this.socket.emit("gemini_message", { text });
    return true;
  }

  captureFrame() {
    if (!this.socket || !this.socket.connected) {
      console.error(
        "GeminiSocketService: Cannot capture frame - not connected"
      );
      return false;
    }

    console.log("GeminiSocketService: Requesting frame capture");
    this.socket.emit("gemini_capture");
    return true;
  }

  addMessageHandler(handler) {
    this.messageHandlers.push(handler);
    return () => {
      this.messageHandlers = this.messageHandlers.filter((h) => h !== handler);
    };
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.connected = false;
    }
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