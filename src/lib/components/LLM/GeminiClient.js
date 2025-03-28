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
      // Don't create a new connection if already connected
      if (flaskSocket && flaskSocket.connected) {
        console.log("GeminiClient: Already connected, sending gemini_connect");
        flaskSocket.emit("gemini_connect");
        isConnected = true;
        return true;
      }

      flaskSocket = io(apiUrl, {
        transports: ["websocket", "polling"],
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        timeout: 20000,
        forceNew: false,
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

      // Handle streaming or complete responses
      if (lastMessage && lastMessage.role === "assistant" && !data.complete) {
        // Update existing streaming message
        lastMessage.content = data.content;
        lastMessage.streaming = true;

        if (data.image_path) {
          addImageInfo(lastMessage, data);
        }
      } else if (
        lastMessage &&
        lastMessage.role === "assistant" &&
        data.complete
      ) {
        // Finalize existing message
        lastMessage.content = data.content;
        lastMessage.streaming = false;

        if (data.image_path) {
          addImageInfo(lastMessage, data);
        }

        console.log("PROCESSING COMPLETE MESSAGE - EXISTING MESSAGE");
        processCompleteMessage(lastMessage.content);
      } else {
        // New message
        const newMessage = {
          role: "assistant",
          content: data.content,
          streaming: !data.complete,
        };

        if (data.image_path) {
          addImageInfo(newMessage, data);
        }

        updatedConversation.push(newMessage);

        if (data.complete) {
          console.log("PROCESSING COMPLETE MESSAGE - NEW MESSAGE");
          processCompleteMessage(newMessage.content);
        }
      }
    }

    return {
      conversation: updatedConversation,
      structuredResponse,
      qualityScore,
      isComplete: data.complete || false,
    };

    // Helper function to process a complete message
    function processCompleteMessage(content) {
      structuredResponse = extractStructuredResponse(content);
      qualityScore = extractQualityScore(content);

      // Only proceed if we have rewards
      if (
        structuredResponse.result &&
        structuredResponse.result.rewards &&
        structuredResponse.result.rewards.length > 0
      ) {
        console.log(structuredResponse.result.rewards.length + " REWARDS");

        // IMPORTANT: Only clear rewards ONCE here
        websocketService.send({
          type: "clear_active_rewards",
          preserve_z: true,
        });

        rewardStore.cleanRewardsLocal();

        // Mark rewards as auto_capture
        const rewards = structuredResponse.result.rewards.map((reward) => ({
          ...reward,
          auto_capture: true,
          id: reward.id || uuidFn(),
        }));

        // Create weights array (all 1.0 for equal weighting)
        const weights = rewards.map(() => 1.0);

        // Wait a moment to ensure the clear completes first
        setTimeout(() => {
          // Send all rewards in one batch request
          websocketService.send({
            type: "request_reward",
            reward: {
              rewards: rewards,
              weights: weights,
              combinationType:
                structuredResponse.result.combinationType || "geometric",
            },
            add_to_existing: true,
            batch_mode: true,
            timestamp: new Date().toISOString(),
          });

          // Update the local reward store
          rewardStore.setRewards(rewards);

          console.log(
            `Sent ${rewards.length} rewards in a single batch request`
          );
        }, 100);
      } else {
        console.log("NO REWARDS FOUND IN RESPONSE");
      }
    }

    // Helper to add image info to message
    function addImageInfo(message, data) {
      message.imagePath = data.image_path;
      message.imageTimestamp = data.image_timestamp || Date.now();
      message.image_path = data.image_path;
      message.image_timestamp = data.image_timestamp || Date.now();
    }
  };

  const extractQualityScore = (content) => {
    try {
      // First attempt: Try to extract from JSON inside code blocks
      const codeBlockRegex = /```json\s*({[\s\S]*?})\s*```/;
      const codeMatch = content.match(codeBlockRegex);

      if (codeMatch && codeMatch[1]) {
        try {
          const jsonData = JSON.parse(codeMatch[1]);
          if (jsonData.quality_score !== undefined) {
            const score = parseFloat(jsonData.quality_score);
            if (!isNaN(score) && score >= 0 && score <= 1) {
              return score;
            }
          }
        } catch (jsonError) {
          console.log("Failed to parse JSON from code block", jsonError);
          // Continue to next method if JSON parsing fails
        }
      }

      // Second attempt: Try the original regex method
      const qualityRegex = /quality[_\s]?score[:\s]*([0-9]*\.?[0-9]+)/i;
      const match = content.match(qualityRegex);

      if (match && match[1]) {
        const score = parseFloat(match[1]);
        if (!isNaN(score) && score >= 0 && score <= 1) {
          return score;
        }
      }

      return null;
    } catch (error) {
      console.error("Error extracting quality score", error);
      return null;
    }
  };

  const checkConnection = () => {
    const socketConnected = flaskSocket && flaskSocket.connected;

    if (socketConnected) {
      console.log("GeminiClient: Checking connection status");
      flaskSocket.emit("gemini_connect");
      flaskSocket.emit("check_gemini_connection");
      isConnected = true;
    } else if (flaskSocket) {
      // Try to reconnect if socket exists but is disconnected
      console.log("GeminiClient: Socket exists but disconnected, reconnecting");
      flaskSocket.connect();
      flaskSocket.emit("gemini_connect");
    } else {
      console.log("GeminiClient: No socket connection available");
      isConnected = false;
    }

    return socketConnected;
  };

  const sendMessage = (message, options = {}) => {
    if (!flaskSocket || !flaskSocket.connected) {
      addSystemMessage(
        "Error: Could not send message - Gemini service not connected"
      );
      return Promise.resolve(false);
    }

    return new Promise(async (resolve) => {
      try {
        const messageId = options.id || uuidFn();
        const frameCaptureResult = await captureFrame();

        console.log("FRAME CAPTURE RESULT:", frameCaptureResult);

        flaskSocket.emit("gemini_message", {
          message,
          id: messageId,
          add_to_existing: options.add_to_existing || false,
          include_image: options.include_image !== false,
          frame_url: frameCaptureResult?.frameUrl,
          positions: frameCaptureResult?.positions,
          auto_correct: options.auto_correct || false,
        });
        resolve(true);
      } catch (error) {
        console.error("Error in sendMessage:", error);
        addSystemMessage("Error: Problem sending message");
        resolve(false);
      }
    });
  };

  const captureFrame = () => {
    return new Promise(async (resolve) => {
      try {
        if (websocketService.getSocket()?.readyState !== WebSocket.OPEN) {
          resolve({ success: false, error: "WebSocket not connected" });
          return;
        }

        const requestId = uuidFn();
        let responseTimeout;
        let frameData = null;
        let positionsData = null;

        // Handler for both frame capture and target positions
        const messageHandler = (data) => {
          if (data.type === "frame_captured" && data.requestId === requestId) {
            frameData = data;
            checkAndResolve();
          } else if (
            data.type === "target_positions" &&
            data.requestId === requestId
          ) {
            positionsData = data;
            checkAndResolve();
          }
        };

        // Helper to check if we have both responses and resolve
        const checkAndResolve = () => {
          if (frameData && positionsData) {
            clearTimeout(responseTimeout);
            cleanup();

            console.log("FRAME DATA:", frameData);
            console.log("POSITIONS DATA:", positionsData);

            if (frameData.status === "success" && frameData.frame_path) {
              resolve({
                success: true,
                frameUrl: frameData.frame_path,
                fullUrl: frameData.frame_path,
                positions: positionsData.data || {},
                positionStatus: positionsData.status,
              });
            } else {
              resolve({
                success: false,
                error: frameData.error || "Missing frame_path",
                positions: positionsData.data || {},
                positionStatus: positionsData.status,
              });
            }
          }
        };

        const cleanup = websocketService.addMessageHandler(messageHandler);

        responseTimeout = setTimeout(() => {
          cleanup();
          resolve({ success: false, error: "Timeout" });
        }, 5000);

        // Send both requests
        websocketService.send({
          type: "capture_frame",
          requestId: requestId,
          timestamp: new Date().toISOString(),
        });

        websocketService.send({
          type: "get_target_positions",
          requestId: requestId,
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        console.error("Error requesting frame and positions:", error);
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
