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
  import { createClaudeClient } from './LLM/ClaudeClient.js';
  import { processRewards } from './LLM/utils.js';
  
  // Import styles
  import './LLM/styles.css';

  const API_URL = import.meta.env.VITE_API_URL;
  
  // State variables
  let prompt = $state('');
  let isProcessing = $state(false);
  let chatContainer;
  let cleanupHandler;
  let cleanupGeminiHandler;
  
  let selectedModel = $state('claude');
  let isGeminiConnected = $state(false);
  let autoCapture = $state(false);
  let captureInterval = $state(null);
  let lastCaptureTime = $state(0);
  let claudeConversation = $state([]);
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

  // Initialize markdown parser
  const md = new MarkdownIt({
    html: false,
    breaks: true,
    linkify: true
  });

  // Create clients
  const geminiClient = createGeminiClient(rewardStore, websocketService, addSystemMessage, uuidv4);
  const claudeClient = createClaudeClient(chatStore, rewardStore, websocketService, uuidv4);
  
  // When chatStore updates or model changes, update the appropriate conversation
  $effect(() => {
    if (selectedModel === 'claude') {
      if ($chatStore.conversation && $chatStore.conversation.length > 0) {
        claudeConversation = [...$chatStore.conversation];
      }
    } else {
      if ($chatStore.conversation && $chatStore.conversation.length > 0) {
        geminiConversation = [...$chatStore.conversation];
      }
    }
  });

  // Update the appropriate conversation
  function updateConversation(newConversation) {
    if (selectedModel === 'claude') {
      claudeConversation = newConversation;
      
      // Update the chatStore only if Claude is selected (for API calls)
      chatStore.update(store => ({
        ...store,
        conversation: newConversation
      }));
    } else {
      geminiConversation = newConversation;
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
    
    // WebSocket handler for the main WebRTC server
    cleanupHandler = websocketService.addMessageHandler((data) => {
      if (data.type === 'llm_response') {
        isProcessing = false;
      } else if (data.type === 'debug_model_info') {
        // Store computation status for use in the UI
        isComputingRewards = data.is_computing;
      }
    });
    
    // WebSocket handler specifically for Gemini messages
    cleanupGeminiHandler = geminiSocketService.addMessageHandler((data) => {
      if (data.type === 'gemini_response' || data.type === 'text') {
      
        
        
        
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
        
        // Scroll chat to bottom
        setTimeout(() => {
          chatContainer?.scrollTo({
            top: chatContainer.scrollHeight,
            behavior: 'smooth'
          });
        }, 100);
      } else if (data.type === 'gemini_connection_status') {
        isGeminiConnected = data.connected;
      } else if (data.type === 'frame_captured') {
        // Just handle the error case
        if (!data.success) {
          addSystemMessage(`Error capturing frame: ${data.error || 'Unknown error'}`);
        }
      }
    });
    
    // Set up Gemini client
    geminiClient.connect(API_URL);
    
    // Set up more robust Gemini connection monitoring
    const checkConnectionInterval = setInterval(() => {
      const isConnectedNow = geminiClient.checkConnection();
      
      // If checkConnection returns false, actively try to reconnect
      if (!isConnectedNow) {
        console.log("Gemini connection appears to be down, attempting reconnection...");
        geminiSocketService.reconnect();
      }
    }, 5000);
    
    // Clean up on destroy
    onDestroy(() => {
      clearInterval(checkConnectionInterval);
      
      if (cleanupHandler) {
        cleanupHandler();
      }
      
      geminiClient.disconnect();
      
      stopAutoCapture();
    });

    // Initial state
    isGeminiConnected = geminiSocketService.isConnected();
  });



  function toggleAutoCapture() {
    if (autoCapture) {
      stopAutoCapture();
    } else {
      showAutoCorrectPrompt();
    }
  }
  
  function showAutoCorrectPrompt() {
    // Show a dialog to get the initial prompt for auto-correction
    if (!isGeminiConnected) {
      return;
    }
    
    // Ask for the prompt that should be auto-corrected
    const initialPrompt = prompt.trim() || window.prompt("Enter the goal to auto-correct (what motion do you want to create?)", "");
    
    if (!initialPrompt) {
      return; // User cancelled
    }
    
    autoCorrectPrompt = initialPrompt;
    startAutoCorrect(initialPrompt);
  }

  function startAutoCorrect(initialPrompt) {
    if (!isGeminiConnected || !initialPrompt) {
      return;
    }
    
    autoCapture = true;
    autoCorrectActive = true;
    autoCorrectAttempts = 0;
    autoCorrectQuality = 0;
    
    // Send the initial prompt with current frame
    if (selectedModel === 'gemini') {
      geminiClient.sendMessage(initialPrompt, { 
        add_to_existing: false,
        include_image: true,
        auto_correct: true
      }).catch(error => {
        console.error("Error starting auto-correction:", error);
        addSystemMessage("Error starting auto-correction");
      });
    }
    
    // Set up interval for auto-correction (every 10 seconds)
    autoCorrectInterval = setInterval(async () => {
      // CRITICAL: Wait for rewards computation to finish completely before attempting capture
      if (isComputingRewards) {
        console.log("Rewards are being computed, delaying auto-correction until computation completes");
        return;
      }
      
      // Only continue if we're not already processing a response
      if (!isProcessing) {
        try {
          // First check if humanoid is ready by asking for model info
          // This check will happen before any frame capture attempt
          await checkHumanoidReady();
        } catch (error) {
          console.error("Error in auto-correction cycle:", error);
          addSystemMessage("Error in auto-correction cycle");
        }
      } else if (isComputingRewards) {
        addSystemMessage("Waiting for current reward computation to complete...");
      }
    }, 10000); // Every 10 seconds
    
    addSystemMessage(`Auto-correction started with goal: "${initialPrompt}"`);
  }
  
  function performAutoCorrection() {
    console.log("[DEBUG] performAutoCorrection called - checking conditions...");
    
    // Increment attempts
    autoCorrectAttempts++;
    console.log(`[DEBUG] Auto-correct attempt #${autoCorrectAttempts}`);
    
    // Check if we've reached a satisfactory quality or max attempts
    if (autoCorrectQuality >= 0.8 || autoCorrectAttempts > 20) {
      console.log(`[DEBUG] performAutoCorrection: stopping auto capture due to quality (${autoCorrectQuality}) or attempts (${autoCorrectAttempts})`);
      stopAutoCapture();
      return;
    }
    
    console.log("[DEBUG] performAutoCorrection: quality check passed, continuing...");

    // First verify WebSocket connection is available
    if (websocketService.getSocket()?.readyState !== WebSocket.OPEN) {
      addSystemMessage("WebSocket disconnected. Waiting for reconnection...");
      // Retry after a delay
      setTimeout(performAutoCorrection, 3000);
      return;
    }
    
    // Check if rewards are currently being computed by querying debug info
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
        // Clean up handler and clear timeout
        debugInfoHandler();
        clearTimeout(timeoutId);
        
        // Process the debug info
        proceedWithAutoCorrection(data.is_computing);
      }
    });
    
    // Function to proceed with auto-correction after checking computation status
    function proceedWithAutoCorrection(isComputing) {
      console.log(`[DEBUG] proceedWithAutoCorrection called, isComputing=${isComputing}`);
      
      // Check if rewards are being computed
      if (isComputing) {
        // If computing, schedule retry after short delay
        console.log("[DEBUG] Rewards are being computed, scheduling retry");
        addSystemMessage("Waiting for reward computation to complete before auto-correction...");
        setTimeout(performAutoCorrection, 2000);
        return;
      }
      
      console.log("[DEBUG] Ready to perform auto-correction (not computing)");
      
      // Verify WebSocket is still connected before proceeding
      if (websocketService.getSocket()?.readyState !== WebSocket.OPEN) {
        addSystemMessage("WebSocket disconnected. Waiting for reconnection...");
        setTimeout(performAutoCorrection, 3000);
        return;
      }
      
      // Send a follow-up correction request
      console.log("[DEBUG] Preparing auto-correction prompt");
      const correctionPrompt = `Based on the current frame, improve your previous suggestion to better achieve: "${autoCorrectPrompt}". Rate the current implementation quality from 0.0 to 1.0 and explain how it can be improved. Format your response with a "quality_score" field.`;
      
      if (selectedModel === 'gemini') {
        console.log("[DEBUG] Sending auto-correction to Gemini");
        
        // Set a flag to show we're processing a request
        isProcessing = true;
        
        // This will automatically include the latest frame
        geminiClient.sendMessage(correctionPrompt, { 
          add_to_existing: true, 
          include_image: true,
          auto_correct: true
        }).then(() => {
          console.log("[DEBUG] Auto-correction message sent successfully");
        }).catch(error => {
          console.error("Error sending auto-correction message:", error);
          addSystemMessage("Error in auto-correction process");
        }).finally(() => {
          // Clear the processing flag when done
          isProcessing = false;
          console.log("[DEBUG] Auto-correction message handling complete");
        });
      } else {
        console.log("[DEBUG] Skipping auto-correction - selected model is not Gemini");
      }
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
  }

  // Check if the humanoid is ready before attempting capture
  async function checkHumanoidReady() {
    return new Promise((resolve, reject) => {
      console.log("Checking if humanoid is ready for auto-correction");
      
      // Request debug info to check computing status
      websocketService.send({
        type: "debug_model_info"
      });
      
      // Set a timeout in case we don't get a debug_model_info response
      const timeoutId = setTimeout(() => {
        if (debugInfoHandler) {
          debugInfoHandler(); // Clean up handler
          console.log("Debug info timeout - proceeding anyway");
          resolve(true); // Proceed anyway after timeout
        }
      }, 2000);
      
      // Wait for debug info response before continuing
      const debugInfoHandler = websocketService.addMessageHandler((data) => {
        if (data.type === 'debug_model_info') {
          // Clean up handler and clear timeout
          debugInfoHandler();
          clearTimeout(timeoutId);
          
          // Check if rewards are computing
          isComputingRewards = data.is_computing === true;
          
          if (isComputingRewards) {
            console.log("Humanoid is still computing rewards, will try again later");
            resolve(false); // Not ready yet
          } else {
            console.log("Humanoid is ready for auto-correction, proceeding with capture");
            
            // Now that we know humanoid is ready, capture frame
            captureFrame().then(success => {
              if (success) {
                // Successfully captured frame, perform auto-correction
                performAutoCorrection();
                resolve(true);
              } else {
                console.log("Frame capture failed, skipping this auto-correction cycle");
                resolve(false);
              }
            }).catch(err => {
              console.error("Error capturing frame:", err);
              resolve(false);
            });
          }
        }
      });
    });
  }
  
  async function captureFrame() {
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
    // Get the current conversation based on selected model
    const currentConversation = selectedModel === 'claude' ? claudeConversation : geminiConversation;
    const newConversation = [...currentConversation, {
      role: 'system',
      content: message
    }];
    
    // Update the appropriate conversation
    updateConversation(newConversation);
    
    setTimeout(() => {
      chatContainer?.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
      });
    }, 100);
  }

  async function handleSubmit() {
    if (!prompt.trim()) {
      return;
    }
    
    isProcessing = true;
    const currentPrompt = prompt.trim();
    prompt = '';
    
    // Get the current conversation
    const currentConversation = selectedModel === 'claude' ? claudeConversation : geminiConversation;
    const newConversation = [...currentConversation, {
      role: 'user',
      content: currentPrompt
    }];
    
    // Update the appropriate conversation
    updateConversation(newConversation);
    
    setTimeout(() => {
      chatContainer?.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
      });
    }, 100);
    
    if (selectedModel === 'gemini') {
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
    } else {
      // Claude
      const result = await claudeClient.sendMessage(API_URL, currentPrompt, $chatStore.sessionId, addToExisting);
      if (result.success) {
        claudeConversation = result.conversation;
        
        setTimeout(() => {
          chatContainer?.scrollTo({
            top: chatContainer.scrollHeight,
            behavior: 'smooth'
          });
        }, 100);
      }
      
      isProcessing = false;
    }
  }

  async function clearChat() {
    try {
      if (selectedModel === 'gemini') {
        geminiClient.clearConversation(webrtcService.clientId);
        geminiConversation = [];
      } else {
        // For Claude
        await claudeClient.clearConversation(API_URL, $chatStore.sessionId);
        claudeConversation = [];
      }
    } catch (error) {
      console.error('Error clearing chat', error);
    }
    
    stopAutoCapture();
  }

  function testFlaskConnection() {
    geminiClient.checkConnection();
  }

  function switchModel(model) {
    if (model === selectedModel) return;
    
    // Stop auto-capture if switching from Gemini to Claude
    if (selectedModel === 'gemini' && model === 'claude') {
      stopAutoCapture();
    }
    
    // Update the model
    selectedModel = model;
    
    // Scroll to bottom after a short delay to ensure the new conversation renders
    setTimeout(() => {
      chatContainer?.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
      });
    }, 100);
  }
</script>

<div class="flex flex-col h-[600px]">
  <ModelControls 
    {selectedModel}
    onSwitchModel={switchModel}
    onClearChat={clearChat}
    {isGeminiConnected}
    {autoCapture}
    onToggleAutoCapture={toggleAutoCapture}
    onCaptureFrame={captureFrame}
    onTestFlaskConnection={testFlaskConnection}
  />

  <ChatContainer 
    conversation={selectedModel === 'claude' ? claudeConversation : geminiConversation}
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