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
        transports: ["websocket"],
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        timeout: 20000,
      });

      flaskSocket.on("connect", () => {
        isConnected = true;
        flaskSocket.emit("gemini_connect");
      });

      flaskSocket.on("gemini_connection_status", (data) => {
        isConnected = data.connected;
      });

      flaskSocket.on("connect_error", () => {
        isConnected = false;
      });

      flaskSocket.on("disconnect", () => {
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
            preserve_z: true
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
            
            if (hasMultipleRewards) {
              console.log(`Batch processing ${structuredResponse.result.rewards.length} rewards from Gemini`);
            }
            
            // Mark all rewards as auto_capture to ensure they preserve the environment
            if (structuredResponse.result.rewards) {
              structuredResponse.result.rewards = structuredResponse.result.rewards.map(reward => ({
                ...reward,
                auto_capture: true
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
              preserve_z: true
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
              
              if (hasMultipleRewards) {
                console.log(`Batch processing ${structuredResponse.result.rewards.length} rewards from Gemini`);
              }
              
              // Mark all rewards as auto_capture to ensure they preserve the environment
              if (structuredResponse.result.rewards) {
                structuredResponse.result.rewards = structuredResponse.result.rewards.map(reward => ({
                  ...reward,
                  auto_capture: true
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

      // Do an additional HTTP status check to verify the server is truly responsive
      fetch(`${apiUrl}/api/gemini_status`)
        .then((response) => {
          if (response.ok) {
            return response.json();
          } else {
            throw new Error(`API responded with status ${response.status}`);
          }
        })
        .then((status) => {
          isConnected = status.socketio_connected && status.connected;
        })
        .catch((error) => {
          console.error("Gemini API health check failed:", error);
          // If HTTP check fails but socket appears connected, the connection might be stale
          if (socketConnected) {
            console.warn(
              "Socket appears connected but HTTP check failed - connection may be stale"
            );
            flaskSocket.disconnect(); // Force disconnect to trigger reconnection
            flaskSocket.connect(); // Attempt immediate reconnection
          }
        });
    }

    return socketConnected;
  };

  const sendMessage = (message, options = {}) => {
    if (flaskSocket && flaskSocket.connected) {
      console.log("Sending message to Gemini, starting snapshot sequence");

      // Use a Promise to handle the asynchronous operations
      return new Promise(async (resolve) => {
        try {
          // Capture frame
          console.log("Requesting frame capture...");
          const frameCaptureResult = await captureFrame();
          console.log("Frame capture completed:", frameCaptureResult.success);

          // Log the frame URL if successful
          if (frameCaptureResult.success && frameCaptureResult.frameUrl) {
            console.log("Frame URL:", frameCaptureResult.frameUrl);
          } else {
            console.warn(
              "Frame capture failed or timed out:",
              frameCaptureResult.error || "Unknown reason"
            );
          }

          // Now send the message with image
          console.log("Sending message with image to Gemini");
            
          try {
            flaskSocket.emit("gemini_message", {
              message,
              add_to_existing: options.add_to_existing || false,
              include_image: options.include_image !== false,
              frame_url: frameCaptureResult?.frameUrl,
              auto_correct: options.auto_correct || false
            });
            console.log("Message sent successfully to Gemini");
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

              console.log("Received message from capture frame:", data);

              // Resolve with success/error based on response status
              if (data.status === "success") {
                // Extract the image URL
                const frameUrl = data.frame_path;
                
                // Construct the full URL that the backend can access
                // The API_URL environment variable should be something like "http://localhost:5000"
                const baseUrl = import.meta.env.VITE_API_URL || window.location.origin;
                
                // Ensure frameUrl starts with a slash
                // The server expects a URL path that starts with a slash, followed by
                // the path relative to the server's static folder, which is usually "public"
                
                // The URL should look like "/storage/shared_frames/filename.jpg" 
                const formattedUrl = frameUrl.startsWith('/') ? frameUrl : `/${frameUrl}`;
                
                // For debugging: create a complete URL that could be accessed in a browser
                const fullUrl = `${baseUrl}${formattedUrl}`;
                
                console.log("Frame captured successfully, URL (relative):", frameUrl);
                console.log("Frame URL (full):", fullUrl);
                
                // Return both URLs
                resolve({ 
                  success: true, 
                  frameUrl: frameUrl,  // Keep the original for backward compatibility
                  fullUrl: fullUrl     // Add the full URL that the backend can access
                });
              } else {
                console.warn(
                  "Frame capture failed:",
                  data.error || "Unknown error"
                );
                resolve({ success: false, error: data.error });
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
