<script>
  import { websocketService } from '../services/websocket';
  import { onMount, onDestroy } from 'svelte';
  import { v4 as uuidv4 } from 'uuid';
  import { rewardStore } from '../stores/rewardStore';
  import { chatStore } from '../stores/chatStore';
  import { webrtcService } from '../services/webrtc';
  import geminiSocketService from '../services/gemini';
  import MarkdownIt from 'markdown-it';
  
  // Import LLM components
  import ModelControls from './LLM/ModelControls.svelte';
  import ChatContainer from './LLM/ChatContainer.svelte';
  import ChatInput from './LLM/ChatInput.svelte';
  import { createGeminiClient } from './LLM/GeminiClient.js';
  
  // Import styles
  import './LLM/styles.css';

  const API_URL = import.meta.env.VITE_API_URL;
  
  // State variables
  let prompt = $state('');
  let isProcessing = $state(false);
  let chatContainer;
  let cleanupHandler;
  
  let selectedModel = $state('gemini');
  let isGeminiConnected = $state(false);
  let autoCapture = $state(false);
  let captureInterval = $state(null);
  let lastCaptureTime = $state(0);
  let geminiConversation = $state([]);
  let structuredResponse = $state(null);
  let addToExisting = $state(false);
  let isComputingRewards = $state(false);
  
  // Auto-correction related states
  let autoCorrectPrompt = $state("");
  let autoCorrectActive = $state(false);
  let autoCorrectQuality = $state(0);
  let autoCorrectInterval = $state(null);
  let autoCorrectAttempts = $state(0);

  // Connection management
  let lastActivityTime = $state(Date.now());
  let inactivityTimeout = $state(null);
  const INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

  // Initialize markdown parser
  const md = new MarkdownIt({
    html: false,
    breaks: true,
    linkify: true
  });

  // Create clients
  const geminiClient = createGeminiClient(rewardStore, websocketService, addSystemMessage, uuidv4);
  
  // When chatStore updates, update gemini conversation
  $effect(() => {
    if ($chatStore.conversation?.length > 0) {
      geminiConversation = [...$chatStore.conversation];
    }
  });

  // Update conversation
  function updateConversation(newConversation) {
    geminiConversation = newConversation;
  }

  function updateActivityTime() {
    lastActivityTime = Date.now();
    resetInactivityTimeout();
  }

  function resetInactivityTimeout() {
    if (inactivityTimeout) {
      clearTimeout(inactivityTimeout);
    }
    
    inactivityTimeout = setTimeout(() => {
      if (isGeminiConnected && !isProcessing && !autoCapture) {
        console.log("Disconnecting Gemini due to inactivity");
        geminiClient.disconnect();
        isGeminiConnected = false;
      }
    }, INACTIVITY_TIMEOUT_MS);
  }

  function ensureGeminiConnection() {
    updateActivityTime();
    
    if (!isGeminiConnected) {
      console.log("Reconnecting to Gemini for active use");
      geminiClient.connect(API_URL);
      
      // Check connection status after a brief delay
      setTimeout(() => {
        isGeminiConnected = geminiSocketService.isConnected();
      }, 1000);
    }
  }

  onMount(() => {
    console.log('LLM component mounted');
    
    if (!$chatStore.sessionId) {
      chatStore.update(store => ({
        ...store,
        sessionId: uuidv4()
      }));
    }
    
    // Listen for gemini-message custom events from GeminiClient
    const geminiMessageHandler = (event) => {
      const data = event.detail;
      console.log("LLM.svelte: Received gemini-message event", data.type);
      
      if (data.type === 'gemini_response') {
        const result = geminiClient.handleResponse(data, geminiConversation);
        geminiConversation = result.conversation;
        
        if (result.structuredResponse) {
          structuredResponse = result.structuredResponse;
        }
        
        // Handle quality score for auto-correction
        if (result.qualityScore !== null && autoCorrectActive) {
          autoCorrectQuality = result.qualityScore;
          addSystemMessage(`Auto-correction quality: ${Math.round(result.qualityScore * 100)}% (attempt ${autoCorrectAttempts})`);
          
          // If quality score is high enough, stop auto-correction
          if (result.qualityScore >= 0.8) {
            addSystemMessage(`Auto-correction reached target quality! (${Math.round(result.qualityScore * 100)}%)`);
            stopAutoCapture();
          }
        }
        
        if (result.isComplete) {
          isProcessing = false;
        }
        
        scrollChatToBottom();
      }
    };
    
    // Register the gemini-message event listener
    window.addEventListener('gemini-message', geminiMessageHandler);
    
    // Single WebSocket handler for all message types (except gemini_response which is now handled by the custom event)
    cleanupHandler = websocketService.addMessageHandler((data) => {
      if (data.type === 'llm_response') {
        isProcessing = false;
      } else if (data.type === 'debug_model_info') {
        isComputingRewards = data.is_computing;
      } else if (data.type === 'gemini_connection_status') {
        isGeminiConnected = data.connected;
      } else if (data.type === 'frame_captured' && !data.success) {
        addSystemMessage(`Error capturing frame: ${data.error || 'Unknown error'}`);
      }
    });
    
    // Only connect if there's ongoing interaction or auto-correct
    // Don't connect on component mount to reduce unnecessary connections
    if (autoCapture || geminiConversation.length > 0) {
      ensureGeminiConnection();
    } else {
      // Just check status without forcing a connection
      isGeminiConnected = geminiSocketService.isConnected();
    }
    
    // Initialize inactivity timeout
    resetInactivityTimeout();
    
    // User interaction listeners for activity tracking
    document.addEventListener('click', updateActivityTime);
    document.addEventListener('keydown', updateActivityTime);
    
    // Clean up on destroy
    onDestroy(() => {
      // Clear all intervals and timeouts first
      if (inactivityTimeout) {
        clearTimeout(inactivityTimeout);
      }
      
      // Clean up all WebSocket handlers
      if (cleanupHandler) cleanupHandler();
      
      // Remove the gemini-message event listener
      window.removeEventListener('gemini-message', geminiMessageHandler);
      
      // Remove activity listeners
      document.removeEventListener('click', updateActivityTime);
      document.removeEventListener('keydown', updateActivityTime);
      
      // Always stop auto capture
      stopAutoCapture();
      
      // Clean up Gemini connection - wait a moment before disconnecting
      // to allow any pending operations to complete
      setTimeout(() => {
        if (geminiSocketService.getConnectionCount() <= 1) {
          console.log("LLM component is the last user, disconnecting Gemini client");
          geminiClient.disconnect();
        } else {
          console.log("Other components still using Gemini client, not disconnecting");
        }
      }, 500);
    });
  });

  function scrollChatToBottom() {
    setTimeout(() => {
      chatContainer?.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
      });
    }, 100);
  }

  function toggleAutoCapture() {
    updateActivityTime();
    
    if (autoCapture) {
      stopAutoCapture();
    } else {
      ensureGeminiConnection();
      showAutoCorrectPrompt();
    }
  }
  
  function showAutoCorrectPrompt() {
    updateActivityTime();
    
    if (!isGeminiConnected) {
      ensureGeminiConnection();
      setTimeout(() => {
        if (isGeminiConnected) {
          showAutoCorrectPrompt();
        } else {
          addSystemMessage("Could not connect to Gemini. Please try again.");
        }
      }, 1500);
      return;
    }
    
    // Ask for the prompt that should be auto-corrected
    const initialPrompt = prompt.trim() || window.prompt("Enter the goal to auto-correct (what motion do you want to create?)", "");
    
    if (!initialPrompt) return; // User cancelled
    
    autoCorrectPrompt = initialPrompt;
    startAutoCorrect(initialPrompt);
  }

  function startAutoCorrect(initialPrompt) {
    updateActivityTime();
    
    if (!isGeminiConnected || !initialPrompt) return;
    
    autoCapture = true;
    autoCorrectActive = true;
    autoCorrectAttempts = 0;
    autoCorrectQuality = 0;
    
    // Send the initial prompt with current frame
    geminiClient.sendMessage(initialPrompt, { 
      add_to_existing: false,
      include_image: true,
      auto_correct: true
    }).catch(error => {
      console.error("Error starting auto-correction:", error);
      addSystemMessage("Error starting auto-correction");
    });
    
    // Set up interval for auto-correction (every 10 seconds)
    autoCorrectInterval = setInterval(async () => {
      updateActivityTime();
      
      // Wait for rewards computation to finish before attempting capture
      if (isComputingRewards) {
        console.log("Rewards are being computed, delaying auto-correction until computation completes");
        return;
      }
      
      // Only continue if we're not already processing a response
      if (!isProcessing) {
        try {
          // Check if humanoid is ready first
          const humanoidReady = await checkHumanoidReady();
          
          // Only proceed with auto-correction if the humanoid is ready
          if (humanoidReady) {
            performAutoCorrection();
          } else {
            addSystemMessage("Humanoid not ready, waiting for next cycle...");
          }
        } catch (error) {
          console.error("Error in auto-correction cycle:", error);
          addSystemMessage("Error in auto-correction cycle: " + error.message);
        }
      } else if (isComputingRewards) {
        addSystemMessage("Waiting for current reward computation to complete...");
      }
    }, 10000); // Every 10 seconds
    
    addSystemMessage(`Auto-correction started with goal: "${initialPrompt}"`);
  }
  
  function performAutoCorrection() {
    updateActivityTime();
    
    // Increment attempts
    autoCorrectAttempts++;
    
    // Check if we've reached a satisfactory quality or max attempts
    if (autoCorrectQuality >= 0.8 || autoCorrectAttempts > 20) {
      stopAutoCapture();
      return;
    }

    // First verify WebSocket connection is available
    if (websocketService.getSocket()?.readyState !== WebSocket.OPEN) {
      addSystemMessage("WebSocket disconnected. Waiting for reconnection...");
      setTimeout(performAutoCorrection, 3000);
      return;
    }
    
    // Check if rewards are currently being computed
    websocketService.send({
      type: "debug_model_info"
    });
    
    // Set a timeout in case we don't get a debug_model_info response
    const timeoutId = setTimeout(() => {
      if (debugInfoHandler) {
        debugInfoHandler(); // Clean up handler
        proceedWithAutoCorrection(false); // Proceed without debug info
      }
    }, 2000);
    
    // Wait for debug info response before continuing
    const debugInfoHandler = websocketService.addMessageHandler((data) => {
      if (data.type === 'debug_model_info') {
        debugInfoHandler();
        clearTimeout(timeoutId);
        proceedWithAutoCorrection(data.is_computing);
      }
    });
    
    // Function to proceed with auto-correction after checking computation status
    function proceedWithAutoCorrection(isComputing) {
      // Check if rewards are being computed
      if (isComputing) {
        addSystemMessage("Waiting for reward computation to complete before auto-correction...");
        setTimeout(performAutoCorrection, 2000);
        return;
      }
      
      // Verify WebSocket is still connected before proceeding
      if (websocketService.getSocket()?.readyState !== WebSocket.OPEN) {
        addSystemMessage("WebSocket disconnected. Waiting for reconnection...");
        setTimeout(performAutoCorrection, 3000);
        return;
      }
      
      // Send a follow-up correction request
      const correctionPrompt = `Based on the current frame, improve your previous suggestion to better achieve: "${autoCorrectPrompt}". Rate the current implementation quality from 0.0 to 1.0 and explain how it can be improved. *mandatory* Add a "quality_score" field to your response.`;
      
      isProcessing = true;
      
      console.log("correctionPrompt", correctionPrompt);
      geminiClient.sendMessage(correctionPrompt, { 
        add_to_existing: true, 
        include_image: true,
        auto_correct: true
      }).catch(error => {
        console.error("Error sending auto-correction message:", error);
        addSystemMessage("Error in auto-correction process");
      }).finally(() => {
        isProcessing = false;
      });
    }
  }

  function stopAutoCapture() {
    if (captureInterval) {
      clearInterval(captureInterval);
      captureInterval = null;
    }
    
    if (autoCorrectInterval) {
      clearInterval(autoCorrectInterval);
      autoCorrectInterval = null;
    }
    
    autoCapture = false;
    autoCorrectActive = false;
    
    if (lastCaptureTime > 0) {
      addSystemMessage('Auto-correction stopped');
    }
    
    updateActivityTime();
  }

  // Check if the humanoid is ready before attempting capture
  async function checkHumanoidReady() {
    updateActivityTime();
    
    return new Promise((resolve, reject) => {
      // Request debug info to check computing status
      websocketService.send({
        type: "debug_model_info"
      });
      
      // Set a timeout in case we don't get a debug_model_info response
      const timeoutId = setTimeout(() => {
        if (debugInfoHandler) {
          debugInfoHandler();
          resolve(true); // Proceed anyway after timeout
        }
      }, 2000);
      
      // Wait for debug info response before continuing
      const debugInfoHandler = websocketService.addMessageHandler((data) => {
        if (data.type === 'debug_model_info') {
          // Clear handler first to prevent multiple calls
          const handler = debugInfoHandler;
          setTimeout(() => handler(), 0); // Allow this function to complete first
          clearTimeout(timeoutId);
          
          console.log("Received debug_model_info:", data.is_computing);
          
          // Check if rewards are computing
          isComputingRewards = data.is_computing === true;
          
          if (isComputingRewards) {
            console.log("Humanoid is computing rewards - not ready");
            resolve(false); // Not ready yet
          } else {
            console.log("Humanoid is ready - returning true");
            resolve(true); // Just resolve, don't capture frame or auto-correct here
          }
        }
      });
    });
  }
  
  async function captureFrame() {
    updateActivityTime();
    
    // Ensure Gemini is connected before capturing
    if (!isGeminiConnected) {
      ensureGeminiConnection();
      
      // Wait for connection before capturing
      if (!isGeminiConnected) {
        const connected = await new Promise(resolve => {
          const checkInterval = setInterval(() => {
            if (isGeminiConnected) {
              clearInterval(checkInterval);
              resolve(true);
            }
          }, 200);
          
          // Timeout after 3 seconds
          setTimeout(() => {
            clearInterval(checkInterval);
            resolve(false);
          }, 3000);
        });
        
        if (!connected) {
          addSystemMessage('Error: Could not connect to Gemini for frame capture');
          return false;
        }
      }
    }
    
    try {
      // Wait for the captureFrame Promise to resolve
      const result = await geminiClient.captureFrame();
      
      if (result) {
        lastCaptureTime = Date.now();
        return true;
      } else {
        addSystemMessage('Error: Could not capture frame - service error or timeout');
        return false;
      }
    } catch (error) {
      console.error("Error in captureFrame:", error);
      addSystemMessage('Error: Could not capture frame - unexpected error');
      return false;
    }
  }

  function addSystemMessage(message) {
    // Add system message to conversation
    const newConversation = [...geminiConversation, {
      role: 'system',
      content: message
    }];
    
    // Update conversation
    updateConversation(newConversation);
    scrollChatToBottom();
  }

  async function handleSubmit() {
    if (!prompt.trim()) return;
    
    // Ensure connection before sending message
    ensureGeminiConnection();
    
    isProcessing = true;
    const currentPrompt = prompt.trim();
    prompt = '';
    
    // Add user message to conversation
    const newConversation = [...geminiConversation, {
      role: 'user',
      content: currentPrompt
    }];
    
    // Update conversation
    updateConversation(newConversation);
    scrollChatToBottom();
    
    // Send message to Gemini
    geminiClient.sendMessage(currentPrompt, { add_to_existing: addToExisting })
      .then(result => {
        if (!result) {
          isProcessing = false;
        }
      })
      .catch(error => {
        console.error("Error sending message to Gemini:", error);
        addSystemMessage("Error sending message to Gemini");
        isProcessing = false;
      });
  }

  async function clearChat() {
    updateActivityTime();
    
    try {
      // Clear client-side conversation first
      geminiConversation = [];
      
      // Clear server-side conversation
      geminiClient.clearConversation(webrtcService.clientId);
      
      // Reconnect to fully reset the session
      setTimeout(() => {
        geminiClient.disconnect();
        setTimeout(() => {
          geminiClient.connect(API_URL);
          testFlaskConnection();
        }, 500);
      }, 500);
      
      addSystemMessage("Chat and session fully cleared");
    } catch (error) {
      console.error('Error clearing chat', error);
      addSystemMessage("Error clearing chat: " + error.message);
    }
    
    stopAutoCapture();
  }

  function testFlaskConnection() {
    updateActivityTime();
    ensureGeminiConnection();
    geminiClient.checkConnection();
  }
</script>

<div class="flex flex-col h-[600px]">
  <ModelControls 
    {selectedModel}
    onSwitchModel={() => {}}
    onClearChat={clearChat}
    {isGeminiConnected}
    {autoCapture}
    onToggleAutoCapture={toggleAutoCapture}
    onCaptureFrame={captureFrame}
    onTestFlaskConnection={testFlaskConnection}
  />

  <ChatContainer 
    conversation={geminiConversation}
    {selectedModel}
    {structuredResponse}
    bind:chatContainer={chatContainer}
  />

  <ChatInput 
    bind:prompt
    {isProcessing}
    {selectedModel}
    bind:addToExisting
    onSubmit={handleSubmit}
  />
</div>