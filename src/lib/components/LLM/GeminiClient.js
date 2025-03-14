// GeminiClient.js - Handler for Gemini communication

import { io } from "socket.io-client";
import { extractStructuredResponse, processRewards } from "./utils.js";
import { v4 as uuidv4 } from "uuid";

/**
 * Creates a Gemini client for handling Gemini Vision model communication
 */
export function createGeminiClient(
  rewardStore,
  websocketService,
  addSystemMessage,
  uuidFn = uuidv4
) {
  let flaskSocket = null;
  let isConnected = false;
  let apiUrl;

  const connect = (url) => {
    apiUrl = url;
    try {
      flaskSocket = io(apiUrl, {
        transports: ["websocket", "polling"], // Allow polling fallback if websocket fails
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        timeout: 20000,
        forceNew: false, // Don't force new connection to allow socket.io manager to reuse connections
      });

      flaskSocket.on("connect", () => {
        console.log("GeminiClient: Connected to Gemini service");
        isConnected = true;
        flaskSocket.emit("gemini_connect");
      });

      flaskSocket.on("gemini_connection_status", (data) => {
        isConnected = data.connected;
      });

      flaskSocket.on("connect_error", (error) => {
        console.error("GeminiClient: Connection error", error.message);
        isConnected = false;
      });

      flaskSocket.on("disconnect", () => {
        console.log("GeminiClient: Disconnected from Gemini service");
        isConnected = false;
      });

      return true;
    } catch (error) {
      console.error("Flask socket setup error", error);
      return false;
    }
  };

  const handleResponse = (data, geminiConversation) => {
    let updatedConversation = [...geminiConversation];
    let structuredResponse = null;
    let qualityScore = null;

    if (data.content) {
      const lastMessage = updatedConversation[updatedConversation.length - 1];

      // Check if this is part of streaming response
      if (lastMessage && lastMessage.role === "assistant" && !data.complete) {
        lastMessage.content = data.content;
        lastMessage.streaming = true;
        // Add image info if available (store both camelCase and snake_case for compatibility)
        if (data.image_path) {
          lastMessage.imagePath = data.image_path;
          lastMessage.imageTimestamp = data.image_timestamp || Date.now();
          // Also keep original names for consistency
          lastMessage.image_path = data.image_path;
          lastMessage.image_timestamp = data.image_timestamp || Date.now();
        }
      } else {
        // Final message or new message
        if (lastMessage && lastMessage.role === "assistant" && data.complete) {
          lastMessage.content = data.content;
          lastMessage.streaming = false;

          // Add image info if available (store both camelCase and snake_case for compatibility)
          if (data.image_path) {
            lastMessage.imagePath = data.image_path;
            lastMessage.imageTimestamp = data.image_timestamp || Date.now();
            // Also keep original names for consistency
            lastMessage.image_path = data.image_path;
            lastMessage.image_timestamp = data.image_timestamp || Date.now();
          }

          // Extract structured data when complete
          structuredResponse = extractStructuredResponse(data.content);

          // Look for quality score in auto-correct responses
          qualityScore = extractQualityScore(data.content);

          // For Gemini responses, always clear the rewards list but preserve the environment
          // First, clear rewards but preserve the environment context (current_z)
          websocketService.send({
            type: "clear_active_rewards",
            preserve_z: true,
          });

          // Clean local rewards store for UI
          rewardStore.cleanRewardsLocal();

          // Process new rewards (if any)
          const addToExisting = true; // Always add to existing (empty but preserved environment)
          if (structuredResponse.result) {
            // Enable batch mode for multiple rewards
            const hasMultipleRewards =
              structuredResponse.result.rewards &&
              structuredResponse.result.rewards.length > 1;

            // Mark all rewards as auto_capture to ensure they preserve the environment
            if (structuredResponse.result.rewards) {
              structuredResponse.result.rewards =
                structuredResponse.result.rewards.map((reward) => ({
                  ...reward,
                  auto_capture: true,
                }));
            }

            processRewards(
              structuredResponse.result,
              rewardStore,
              websocketService,
              uuidFn,
              addToExisting
            );
          }
        } else {
          const newMessage = {
            role: "assistant",
            content: data.content,
            streaming: !data.complete,
          };

          // Add image info if available (store both camelCase and snake_case for compatibility)
          if (data.image_path) {
            newMessage.imagePath = data.image_path;
            newMessage.imageTimestamp = data.image_timestamp || Date.now();
            // Also keep original names for consistency
            newMessage.image_path = data.image_path;
            newMessage.image_timestamp = data.image_timestamp || Date.now();
          }

          updatedConversation.push(newMessage);

          // Extract structured data if complete
          if (data.complete) {
            structuredResponse = extractStructuredResponse(data.content);

            // Look for quality score in auto-correct responses
            qualityScore = extractQualityScore(data.content);

            // For Gemini responses, always clear the rewards list but preserve the environment
            // First, clear rewards but preserve the environment context (current_z)
            websocketService.send({
              type: "clear_active_rewards",
              preserve_z: true,
            });

            // Clean local rewards store for UI
            rewardStore.cleanRewardsLocal();

            // Process new rewards (if any)
            const addToExisting = true; // Always add to existing (empty but preserved environment)
            if (structuredResponse.result) {
              // Enable batch mode for multiple rewards
              const hasMultipleRewards =
                structuredResponse.result.rewards &&
                structuredResponse.result.rewards.length > 1;

              // Mark all rewards as auto_capture to ensure they preserve the environment
              if (structuredResponse.result.rewards) {
                structuredResponse.result.rewards =
                  structuredResponse.result.rewards.map((reward) => ({
                    ...reward,
                    auto_capture: true,
                  }));
              }

              processRewards(
                structuredResponse.result,
                rewardStore,
                websocketService,
                uuidFn,
                addToExisting
              );
            }
          }
        }
      }
    }

    return {
      conversation: updatedConversation,
      structuredResponse,
      qualityScore,
      isComplete: data.complete || false,
    };
  };

  // Helper function to extract quality score from a response
  const extractQualityScore = (content) => {
    try {
      // Try to find a quality score in the text
      const qualityRegex = /quality[_\s]?score[:\s]*([0-9]*\.?[0-9]+)/i;
      const match = content.match(qualityRegex);

      if (match && match[1]) {
        const score = parseFloat(match[1]);
        if (!isNaN(score) && score >= 0 && score <= 1) {
          console.log(`Found quality score: ${score}`);
          return score;
        }
      }

      // If we couldn't find a score in the text format, check if there's
      // a quality_score field in structured JSON
      const jsonRegex =
        /```(?:json)?\s*(\{[\s\S]*?\})\s*```|`(\{[\s\S]*?\})`|(\{[\s\S]*?\})/g;
      const matches = [...content.matchAll(jsonRegex)];

      for (const match of matches) {
        const jsonString = (match[1] || match[2] || match[3]).trim();
        try {
          const parsedJson = JSON.parse(jsonString);
          if (parsedJson.quality_score !== undefined) {
            const score = parseFloat(parsedJson.quality_score);
            if (!isNaN(score) && score >= 0 && score <= 1) {
              console.log(`Found quality score in JSON: ${score}`);
              return score;
            }
          }
        } catch (e) {
          // Skip invalid JSON
          continue;
        }
      }

      return null; // No quality score found
    } catch (error) {
      console.error("Error extracting quality score", error);
      return null;
    }
  };

  // Enhanced connection check that also verifies the API endpoint
  const checkConnection = () => {
    const socketConnected = flaskSocket && flaskSocket.connected;

    // If Socket.IO seems connected, emit a check
    if (socketConnected) {
      flaskSocket.emit("gemini_connect");
    }

    return socketConnected;
  };

  const sendMessage = (message, options = {}) => {
    if (flaskSocket && flaskSocket.connected) {
      console.log("Sending message to Gemini");

      // Use a Promise to handle the asynchronous operations
      return new Promise(async (resolve) => {
        try {
          // Generate a unique message ID if not provided
          const messageId = options.id || uuidFn();

          // Capture frame
          const frameCaptureResult = await captureFrame();

          // Now send the message with image
          try {
            flaskSocket.emit("gemini_message", {
              message,
              id: messageId, // Include explicit message ID
              add_to_existing: options.add_to_existing || false,
              include_image: options.include_image !== false,
              frame_url: frameCaptureResult?.frameUrl,
              auto_correct: options.auto_correct || false,
            });
            resolve(true);
          } catch (error) {
            console.error("Error sending message:", error);
            addSystemMessage("Error: Problem sending message");
            resolve(false);
          }
        } catch (error) {
          console.error("Error in sendMessage sequence:", error);
          addSystemMessage("Error: Problem processing message sequence");
          resolve(false);
        }
      });
    } else {
      addSystemMessage(
        "Error: Could not send message - Gemini service not connected"
      );
      return Promise.resolve(false);
    }
  };

  const captureFrame = () => {
    return new Promise((resolve) => {
      try {
        // Use websocketService to send the capture_frame command
        if (websocketService.getSocket()?.readyState === WebSocket.OPEN) {
          // Generate a unique request ID
          const requestId = uuidFn();
          let responseTimeout;

          // Create a one-time message handler
          const messageHandler = (data) => {
            // Check if this is the frame_captured response matching our request
            if (
              data.type === "frame_captured" &&
              data.requestId === requestId
            ) {
              // Clear the timeout and cleanup listener
              clearTimeout(responseTimeout);
              cleanup();

              // Resolve with success/error based on response status
              if (data.status === "success" && data.frame_path) {
                // Extract the image URL
                const frameUrl = data.frame_path;

                // Construct the full URL that the backend can access
                const baseUrl =
                  import.meta.env.VITE_API_URL || window.location.origin;

                // Ensure frameUrl starts with a slash
                const formattedUrl = frameUrl.startsWith("/")
                  ? frameUrl
                  : `/${frameUrl}`;

                // For debugging: create a complete URL that could be accessed in a browser
                const fullUrl = `${baseUrl}${formattedUrl}`;

                // Return both URLs
                resolve({
                  success: true,
                  frameUrl: formattedUrl, // Use the properly formatted URL
                  fullUrl: fullUrl, // Add the full URL that the backend can access
                });
              } else {
                resolve({
                  success: false,
                  error: data.error || "Missing frame_path",
                });
              }
            }
          };

          // Register the message handler
          const cleanup = websocketService.addMessageHandler(messageHandler);

          // Set a timeout to resolve as false if no response within 5 seconds
          responseTimeout = setTimeout(() => {
            cleanup(); // Remove the message handler
            console.warn("Frame capture timed out after 5 seconds");
            resolve({ success: false, error: "Timeout" });
          }, 5000);

          // Send the capture frame command with the request ID
          websocketService.send({
            type: "capture_frame",
            requestId: requestId,
            timestamp: new Date().toISOString(),
          });

          console.log("Frame capture request sent with ID:", requestId);
        } else {
          console.warn("WebSocket not connected, cannot capture frame");
          resolve({ success: false, error: "WebSocket not connected" });
        }
      } catch (error) {
        console.error("Error requesting frame capture:", error);
        resolve({ success: false, error: error.message });
      }
    });
  };

  const disconnect = () => {
    if (flaskSocket) {
      flaskSocket.disconnect();
      flaskSocket = null;
      isConnected = false;
    }
  };

  const clearConversation = (clientId) => {
    const ws = websocketService.getSocket();
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "gemini_clear_conversation",
          client_id: clientId,
        })
      );
      return true;
    }
    return false;
  };

  return {
    connect,
    handleResponse,
    checkConnection,
    sendMessage,
    captureFrame,
    disconnect,
    clearConversation,
    getIsConnected: () => isConnected,
  };
}
