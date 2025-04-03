// GeminiClient.js - Handler for Gemini communication
import { io } from "socket.io-client";
import { extractStructuredResponse, processRewards } from "./utils.js";
import { v4 as uuidv4 } from "uuid";

// Global counter for unique request IDs to prevent duplication
let frameRequestCounter = 0;

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

  // Socket.io connection configuration
  const socketConfig = {
    transports: ["polling", "websocket"],
    reconnection: true,
    reconnectionAttempts: 5,
    reconnectionDelay: 1000,
    timeout: 10000,
    autoConnect: true,
    forceNew: true,
    path: '/socket.io'
  };

  const connect = (url) => {
    apiUrl = url;
    try {
      cleanupSocket();

      console.log("GeminiClient: Creating new connection to", apiUrl);
      flaskSocket = io(apiUrl, socketConfig);
      setupSocketListeners();
      return true;
    } catch (error) {
      console.error("Flask socket setup error", error);
      return false;
    }
  };

  // Clean up any existing socket
  const cleanupSocket = () => {
    if (flaskSocket) {
      console.log("GeminiClient: Cleaning up existing socket");
      try {
        flaskSocket.disconnect();
      } catch (err) {
        console.error("Error disconnecting socket:", err);
      }
      flaskSocket = null;
    }
  };

  // Set up all socket event listeners
  const setupSocketListeners = () => {
    flaskSocket.on("connect", () => {
      console.log("GeminiClient: Connected to Gemini service");
      isConnected = true;
      flaskSocket.emit("gemini_connect");
    });

    flaskSocket.on("gemini_connection_status", (data) => {
      isConnected = data.connected;
    });

    // Relay Gemini responses via custom events
    flaskSocket.on("gemini_response", (data) => {
      console.log("GeminiClient: Received response", data.complete ? "(complete)" : "(streaming)");
      
      window.dispatchEvent(new CustomEvent('gemini-message', { 
        detail: {
          type: "gemini_response",
          ...data
        }
      }));
    });

    flaskSocket.on("connect_error", (error) => {
      console.error("GeminiClient: Connection error", error.message);
      isConnected = false;
    });

    flaskSocket.on("disconnect", () => {
      console.log("GeminiClient: Disconnected from Gemini service");
      isConnected = false;
    });
  };

  // Helper function to update the latest system message
  /**
   * Updates system message in conversation
   */
  const updateLatestSystemMessage = (newText) => {
    addSystemMessage(newText);
  };

  /**
   * Handle Gemini API responses and update conversation
   */
  const handleResponse = (data, geminiConversation) => {
    let updatedConversation = [...geminiConversation];
    let structuredResponse = null;
    let qualityScore = null;

    if (data.content) {
      const lastMessage = updatedConversation[updatedConversation.length - 1];
      const isExistingAssistantMessage = lastMessage && lastMessage.role === "assistant";
      
      if (isExistingAssistantMessage && !data.complete) {
        // Update existing streaming message
        updateExistingMessage(lastMessage, data, false);
      } else if (isExistingAssistantMessage && data.complete) {
        // Finalize existing message
        updateExistingMessage(lastMessage, data, true);
        processCompleteMessage(lastMessage.content);
      } else {
        // Create new message
        const newMessage = createNewMessage(data);
        updatedConversation.push(newMessage);
        
        if (data.complete) {
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
    
    // Helper to update existing message
    function updateExistingMessage(message, data, isComplete) {
      message.content = data.content;
      message.streaming = !isComplete;
      
      if (data.image_path) {
        addImageInfo(message, data);
      }
    }
    
    // Helper to create a new message
    function createNewMessage(data) {
      const message = {
        role: "assistant",
        content: data.content,
        streaming: !data.complete,
      };
      
      if (data.image_path) {
        addImageInfo(message, data);
      }
      
      return message;
    }

    // Helper function to process a complete message
    function processCompleteMessage(content) {
      structuredResponse = extractStructuredResponse(content);
      qualityScore = extractQualityScore(content);

      const hasRewards = structuredResponse.result?.rewards?.length > 0;
      if (!hasRewards) {
        console.log("No rewards found in response");
        return;
      }

      console.log("GeminiClient: Found rewards in response, processing");
      
      // Clear existing rewards
      websocketService.send({
        type: "clear_active_rewards",
        preserve_z: true,
      });
      
      rewardStore.cleanRewardsLocal();

      // Prepare rewards with IDs and auto_capture flag
      const rewards = structuredResponse.result.rewards.map(reward => ({
        ...reward,
        auto_capture: true,
        id: reward.id || uuidFn(),
      }));
      
      // Equal weights for all rewards
      const weights = rewards.map(() => 1.0);

      // Send rewards after a short delay to ensure clear completes
      setTimeout(() => {
        const requestId = `reward_batch_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
        
        websocketService.send({
          type: "request_reward",
          reward: {
            rewards,
            weights,
            combinationType: structuredResponse.result.combinationType || "geometric",
          },
          add_to_existing: true,
          batch_mode: true,
          timestamp: new Date().toISOString(),
          message_id: requestId,
        });

        // Update local state
        rewardStore.setRewards(rewards);
        console.log(`GeminiClient: Sent ${rewards.length} rewards in batch`);
      }, 500);
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

  /**
   * Send a message to Gemini API with optional frame capture
   */
  const sendMessage = (message, options = {}) => {
    // Check connection state
    if (!flaskSocket) {
      addSystemMessage("Error: Could not send message - Gemini service not initialized");
      return Promise.resolve(false);
    }
    
    if (!flaskSocket.connected) {
      addSystemMessage("Error: Could not send message - Gemini service disconnected. Trying to reconnect...");
      flaskSocket.connect();
      return Promise.resolve(false);
    }

    return new Promise(async (resolve) => {
      try {
        addSystemMessage("Capturing frame...");
        const messageId = options.id || uuidFn();
        
        // Set timeout for frame capture (8 seconds)
        const captureTimeout = setTimeout(() => {
          console.warn("Frame capture timeout - continuing without image");
          updateLatestSystemMessage("Frame capture timed out, continuing without image");
          sendMessageToGemini(message, messageId, options, null);
          resolve(true);
        }, 8000);
        
        // Try to capture frame
        try {
          const frameCaptureResult = await captureFrame();
          clearTimeout(captureTimeout);
          
          if (frameCaptureResult && frameCaptureResult.success) {
            // Frame capture succeeded
            updateLatestSystemMessage("Frame captured successfully, sending to Gemini...");
            
            // Add body positions to message if available
            const enhancedMessage = addBodyPositionsToMessage(message, frameCaptureResult);
            
            // Send message with frame
            sendMessageToGemini(enhancedMessage, messageId, options, frameCaptureResult);
          } else {
            // Frame capture failed but we got a response
            updateLatestSystemMessage("Error capturing frame: " + (frameCaptureResult?.error || "Unknown error"));
            sendMessageToGemini(message, messageId, options, null);
          }
        } catch (captureError) {
          // Exception during frame capture
          clearTimeout(captureTimeout);
          updateLatestSystemMessage("Error capturing frame: " + captureError.message);
          sendMessageToGemini(message, messageId, options, null);
        }
        
        resolve(true);
      } catch (error) {
        console.error("Error in sendMessage:", error);
        addSystemMessage("Error: Problem sending message: " + error.message);
        resolve(false);
      }
    });
  };
  
  /**
   * Helper to send a message to Gemini API
   */
  const sendMessageToGemini = (message, messageId, options, frameCaptureResult) => {
    // Prepare message payload
    const payload = {
      message,
      id: messageId,
      add_to_existing: options.add_to_existing || false,
      include_image: frameCaptureResult ? options.include_image !== false : false,
      auto_correct: options.auto_correct || false
    };
    
    // Add frame data if available
    if (frameCaptureResult) {
      payload.frame_url = frameCaptureResult.frameUrl;
      payload.positions = frameCaptureResult.positions;
    }
    
    // Send message
    flaskSocket.emit("gemini_message", payload);
  };
  
  /**
   * Add body positions to message text
   */
  const addBodyPositionsToMessage = (message, frameCaptureResult) => {
    let bodyPositionsAsString = "{}";
    
    if (frameCaptureResult?.positions?.all_body_positions) {
      try {
        bodyPositionsAsString = JSON.stringify(frameCaptureResult.positions.all_body_positions);
      } catch (error) {
        console.error("Error processing body positions:", error);
      }
    }
    
    return message + "\n\n" + "BODY POSITIONS: " + bodyPositionsAsString;
  };

  /**
   * Capture a frame from the WebSocket server
   * Returns a promise that resolves to a frame object with:
   * - success: boolean indicating success or failure
   * - frameUrl: URL of the captured frame
   * - positions: body position data (if available)
   */
  const captureFrame = () => {
    frameRequestCounter++; // Ensure unique request ID
    
    return new Promise(async (resolve) => {
      // Check for WebSocket connection
      if (!websocketService.isConnected()) {
        console.error("Cannot capture frame: WebSocket not connected");
        resolve({ success: false, error: "WebSocket not connected" });
        return;
      }

      try {
        // Create unique request ID
        const requestId = `frame_${Date.now()}_${frameRequestCounter}_${uuidFn().slice(0, 8)}`;
        console.log(`Creating frame capture with requestId: ${requestId}`);
        
        // State tracking
        let responseTimeout;
        let frameData = null;
        let positionsData = null;
        let partialTimeout = null;
        let handlers = { message: null, snapshot: null };
        
        // Set up handlers for cleaning up
        const cleanup = () => {
          if (handlers.message) {
            handlers.message();
            handlers.message = null;
          }
          
          if (handlers.snapshot) {
            handlers.snapshot();
            handlers.snapshot = null;
          }
          
          if (partialTimeout) {
            clearTimeout(partialTimeout);
            partialTimeout = null;
          }
        };
        
        // Handler for checking complete response
        const checkAndResolve = () => {
          // If we have both frame and position data, we're done
          if (frameData && positionsData) {
            clearTimeout(responseTimeout);
            cleanup();
            
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
        
        // Handler for frame and position messages
        const messageHandler = (data) => {
          if (data.type === "frame_captured" && data.requestId === requestId) {
            frameData = data;
            
            // Set timeout for positions if we got frame but not positions
            if (!positionsData && !partialTimeout) {
              partialTimeout = setTimeout(() => {
                if (frameData && !positionsData) {
                  console.log("TARGET POSITIONS TAKING TOO LONG - RESOLVING WITH FRAME ONLY");
                  cleanup();
                  clearTimeout(responseTimeout);
                  
                  if (frameData.status === "success" && frameData.frame_path) {
                    resolve({
                      success: true,
                      frameUrl: frameData.frame_path,
                      fullUrl: frameData.frame_path,
                      positions: {},
                      positionStatus: "timed_out",
                    });
                  } else {
                    resolve({
                      success: false,
                      error: frameData.error || "Missing frame_path",
                      positions: {},
                      positionStatus: "timed_out",
                    });
                  }
                }
              }, 1500); // Short timeout for positions
            }
            
            checkAndResolve();
          } 
          else if (data.type === "target_positions" && data.requestId === requestId) {
            positionsData = data;
            if (partialTimeout) {
              clearTimeout(partialTimeout);
              partialTimeout = null;
            }
            checkAndResolve();
          } 
          else if (data.type === "frame_captured" && data.status === "error") {
            // Handle errors even if requestId doesn't match
            console.error("⚠️ Frame capture error:", data.error);
            cleanup();
            clearTimeout(responseTimeout);
            resolve({
              success: false,
              error: data.error || "Unknown frame capture error",
            });
          }
        };
        
        // Handler for snapshot responses
        const snapshotHandler = (data) => {
          if (data.type === "snapshot_created") {
            if (data.status === "success") {
              if (!frameData) {
                frameData = {
                  type: "frame_captured",
                  status: "success",
                  frame_path: data.frame_path || data.timestamped_path || data.public_path,
                  requestId: requestId,
                  timestamp: data.timestamp_str || data.timestamp
                };
                checkAndResolve();
              }
            } else if (data.status === "error") {
              if (!frameData) {
                frameData = {
                  type: "frame_captured",
                  status: "error",
                  error: data.error || "Unknown error creating snapshot",
                  requestId: requestId
                };
                checkAndResolve();
              }
            }
          }
        };
        
        // Register message handlers
        handlers.message = websocketService.addMessageHandler(messageHandler);
        handlers.snapshot = websocketService.addMessageHandler(snapshotHandler);
        
        // Request a snapshot
        websocketService.send({
          type: "make_snapshot",
          requestId: requestId,
          timestamp: new Date().toISOString(),
        });
        
        // Request target positions after delay
        setTimeout(() => {
          websocketService.send({
            type: "get_target_positions",
            requestId: requestId,
            timestamp: new Date().toISOString(),
          });
          
          // Retry position request after delay if needed
          setTimeout(() => {
            if (!positionsData) {
              websocketService.send({
                type: "get_target_positions",
                requestId: requestId,
                timestamp: new Date().toISOString(),
              });
            }
          }, 2000);
        }, 500);
        
        // Set overall timeout
        responseTimeout = setTimeout(() => {
          // Return partial result if we have frame but no positions
          if (frameData && frameData.status === "success" && frameData.frame_path) {
            console.log("⚠️ PARTIAL TIMEOUT - Got frame but no positions data");
            cleanup();
            resolve({
              success: true,
              frameUrl: frameData.frame_path,
              fullUrl: frameData.frame_path,
              positions: {},
              positionStatus: "timed_out",
              partial: true,
            });
          } else {
            // Last resort attempt
            websocketService.send({
              type: "make_snapshot",
              timestamp: new Date().toISOString(),
            });
            
            // Final timeout
            setTimeout(() => {
              cleanup();
              console.log("⚠️ FINAL TIMEOUT - Frame capture failed");
              resolve({
                success: false,
                error: "Timeout waiting for frame capture and target positions",
                positions: positionsData ? positionsData.data || {} : {},
                positionStatus: positionsData ? positionsData.status : "timed_out",
              });
            }, 2000);
          }
        }, 10000);
        
      } catch (error) {
        console.error("Error requesting frame:", error);
        resolve({ success: false, error: error.message });
      }
    });
  };

  /**
   * Disconnect and clean up socket connection
   */
  const disconnect = () => {
    if (!flaskSocket) return;
    
    console.log("GeminiClient: Disconnecting socket");
    try {
      // Clean up event listeners and close connection
      flaskSocket.removeAllListeners();
      flaskSocket.disconnect();
      
      // Force close the engine for good measure
      if (flaskSocket.io?.engine) {
        flaskSocket.io.engine.close();
      }
    } catch (err) {
      console.error("Error during client disconnect:", err);
    }
    
    // Reset state
    flaskSocket = null;
    isConnected = false;
    console.log("GeminiClient: Socket disconnected and reset");
  };

  /**
   * Clear the conversation history on the server
   */
  const clearConversation = (clientId) => {
    if (!websocketService.isConnected()) {
      return false;
    }
    
    websocketService.send({
      type: "gemini_clear_conversation",
      client_id: clientId
    });
    return true;
  };

  // Return the client API
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
