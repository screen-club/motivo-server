<script>
  import { websocketService } from '../services/websocketService';
  import { onMount, onDestroy } from 'svelte';
  import { v4 as uuidv4 } from 'uuid';
  import { rewardStore } from '../stores/rewardStore';
  import { chatStore } from '../stores/chatStore';
  import { webrtcService } from '../services/webrtcService';
  import geminiSocketService from '../services/geminiSocketService';
  import { io } from 'socket.io-client';

  const API_URL = import.meta.env.VITE_API_URL;
  const FLASK_URL = 'http://localhost:5002';
  
  let flaskSocket = null;

  // Add debug logging function
  function log(message, data = null) {
    const timestamp = new Date().toISOString().substr(11, 12);
    if (data) {
      console.log(`[LLM ${timestamp}]`, message, data);
    } else {
      console.log(`[LLM ${timestamp}]`, message);
    }
  }

  let prompt = $state('');
  let isProcessing = $state(false);
  let chatContainer;
  let showJson = $state(false);
  let cleanupHandler;
  let cleanupGeminiHandler;
  
  let selectedModel = $state('claude');
  let isGeminiConnected = $state(false);
  let autoCapture = $state(false);
  let captureInterval = $state(null);
  let lastCaptureTime = $state(0);

  // Add a state variable for tracking snapshot status
  let lastSnapshotStatus = $state({ success: false, timestamp: 0 });

  // Add model-specific conversation tracking
  let claudeConversation = $state([]);
  let geminiConversation = $state([]);

  // Computed property to get the current model's conversation
  $effect(() => {
    // When chatStore updates or model changes, update the appropriate conversation
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

  // Get the current conversation based on selected model
  function getCurrentConversation() {
    return selectedModel === 'claude' ? claudeConversation : geminiConversation;
  }

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
    log('Component mounted');
    
    if (!$chatStore.sessionId) {
      chatStore.update(store => ({
        ...store,
        sessionId: uuidv4()
      }));
      log('Generated new session ID', $chatStore.sessionId);
    } else {
      log('Using existing session ID', $chatStore.sessionId);
    }
    
    // WebSocket handler for the main WebRTC server
    cleanupHandler = websocketService.addMessageHandler((data) => {
   
      
      if (data.type === 'llm_response') {
        isProcessing = false;
        log('LLM response received from WebRTC server, processing completed');
      }
    });
    
    // WebSocket handler specifically for Gemini messages
    cleanupGeminiHandler = geminiSocketService.addMessageHandler((data) => {
      log('Received GEMINI server message', data);
      if (data.type === 'gemini_response') {
        log('Gemini response received from Flask server');
        handleGeminiResponse(data);
      } else if (data.type === 'text') {
        // Also handle messages with 'text' type
        log('Text response received from Flask server');
        handleGeminiResponse(data); 
      } else if (data.type === 'gemini_connection_status') {
        const newStatus = data.connected;
        log(`Gemini connection status update from Flask server: ${newStatus}`);
        isGeminiConnected = newStatus;
      } else if (data.type === 'audio') {
        // Ignore audio messages
        log('Received audio data from Gemini (ignoring)');
      } else {
        log('Received unknown message type:', data.type);
      }
    });
    
    // Check if websocket is connected
    const ws = websocketService.getSocket();
    log('WebSocket initial state', {
      connected: ws?.readyState === WebSocket.OPEN,
      readyState: ws?.readyState,
      readyStateString: ws ? ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'][ws.readyState] : 'NO_SOCKET'
    });
    
    log('Checking Gemini connection status via dedicated service');
    checkGeminiConnection();
    
    // DIRECT FLASK SOCKET.IO CONNECTION TEST
    log('ATTEMPTING DIRECT FLASK SOCKET.IO CONNECTION TO ' + FLASK_URL);
    
    try {
      flaskSocket = io(FLASK_URL, {
        transports: ['websocket'],
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        timeout: 20000
      });
      
      flaskSocket.on('connect', () => {
        log('FLASK SOCKET.IO CONNECTED SUCCESSFULLY', { id: flaskSocket.id });
        isGeminiConnected = true;
        
        // Test the gemini_connect event
        log('SENDING gemini_connect EVENT TO FLASK');
        flaskSocket.emit('gemini_connect');
      });
      
      flaskSocket.on('error', (error) => {
        log('FLASK SOCKET.IO ERROR', error);
      });
      
      flaskSocket.on('reconnect_attempt', (attemptNumber) => {
        log('FLASK SOCKET.IO RECONNECT ATTEMPT', attemptNumber);
      });
      
      flaskSocket.on('gemini_connection_status', (data) => {
        log('RECEIVED FLASK gemini_connection_status', data);
        isGeminiConnected = data.connected;
      });
      
      flaskSocket.on('connect_error', (error) => {
        log('FLASK SOCKET.IO CONNECTION ERROR', error.message);
        isGeminiConnected = false;
      });
      
      flaskSocket.on('disconnect', () => {
        log('FLASK SOCKET.IO DISCONNECTED');
        isGeminiConnected = false;
      });
      
      flaskSocket.on('gemini_response', (data) => {
        log('RECEIVED FLASK gemini_response', data);
      });
      
    } catch (error) {
      log('FLASK SOCKET.IO SETUP ERROR', error);
    }
    
    // Check socket connection periodically
    const combinedInterval = setInterval(() => {
      // Check geminiSocketService
      log('Periodic Gemini connection check');
      checkGeminiConnection();
      
      // Check direct Flask connection
      if (flaskSocket) {
        log('FLASK SOCKET.IO STATUS CHECK - Connected: ' + flaskSocket.connected);
      }
    }, 5000);
    
    // Clean up on destroy
    onDestroy(() => {
      clearInterval(combinedInterval);
      log('Cleared connection check interval');
      
      if (cleanupHandler) {
        cleanupHandler();
        log('Cleaned up WebRTC handler');
      }
      
      if (flaskSocket) {
        log('DISCONNECTING FROM FLASK SOCKET.IO');
        flaskSocket.disconnect();
        flaskSocket = null;
      }
      
      stopAutoCapture();
    });

    // Initial state
    isGeminiConnected = geminiSocketService.isConnected();
  });

  function checkGeminiConnection() {
    if (flaskSocket && flaskSocket.connected) {
      log('Sending gemini_connect via direct Flask Socket.IO');
      flaskSocket.emit('gemini_connect');
    } else {
      log('Direct Flask Socket.IO not connected');
    }
  }

  function handleGeminiResponse(data) {
    log('Processing Gemini response', data);
    
    if (data.content) {
      // Get the current Gemini conversation
      const newConversation = [...geminiConversation];
      
      const lastMessage = newConversation[newConversation.length - 1];
      
      // Check if this is part of a streaming response (existing assistant message)
      if (lastMessage && lastMessage.role === 'assistant' && !data.complete) {
        log('Appending to existing assistant message (streaming)');
        lastMessage.content = data.content; // Replace with latest content which includes previous chunks
      } else {
        // This is either a new message or the final message of a stream
        if (lastMessage && lastMessage.role === 'assistant' && data.complete) {
          log('Finalizing existing assistant message stream');
          lastMessage.content = data.content;
        } else {
          log('Adding new assistant message');
          newConversation.push({
            role: 'assistant',
            content: data.content
          });
        }
      }
      
      // Update the Gemini conversation directly
      geminiConversation = newConversation;
      
      setTimeout(() => {
        chatContainer?.scrollTo({
          top: chatContainer.scrollHeight,
          behavior: 'smooth'
        });
        log('Scrolled chat to bottom');
      }, 100);
    }
    
    if (data.complete) {
      isProcessing = false;
      log('Processing completed - conversation turn is complete');
    }
  }

  function toggleAutoCapture() {
    log(`Toggle auto-capture. Current state: ${autoCapture}`);
    if (autoCapture) {
      stopAutoCapture();
    } else {
      startAutoCapture();
    }
  }

  function startAutoCapture() {
    if (!isGeminiConnected) {
      log('Cannot start auto-capture - Gemini not connected');
      return;
    }
    
    log('Starting auto-capture');
    autoCapture = true;
    captureInterval = setInterval(() => {
      log('Auto-capture interval triggered');
      captureFrame();
    }, 2000);
    
    // Keep system message for auto-capture start/stop as it's important info
    addSystemMessage('Auto-capture started (1 snapshot every 2 seconds)');
  }

  function stopAutoCapture() {
    if (captureInterval) {
      log('Stopping auto-capture');
      clearInterval(captureInterval);
      captureInterval = null;
    }
    autoCapture = false;
    
    if (lastCaptureTime > 0) {
      addSystemMessage('Auto-capture stopped');
      log('Added system message for auto-capture stopped');
    }
  }

  function captureFrame() {
    log('Requesting frame capture from GeminiSocketService');
    if (geminiSocketService.captureFrame()) {
      lastCaptureTime = Date.now();
      // Update snapshot status instead of adding a system message
      lastSnapshotStatus = { success: true, timestamp: Date.now() };
      log('Snapshot sent to Gemini - updating status indicator');
    } else {
      // Only add system message for errors
      addSystemMessage('Error: Could not capture frame - service not connected');
      lastSnapshotStatus = { success: false, timestamp: Date.now() };
    }
  }

  function addSystemMessage(message) {
    log('Adding system message', message);
    
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
      log('Scrolled chat to bottom after system message');
    }, 100);
  }

  async function handleSubmit() {
    if (!prompt.trim()) {
      log('Empty prompt, not submitting');
      return;
    }
    
    log('Submitting prompt', prompt);
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
      log('Scrolled to bottom after adding user message');
    }, 100);
    
    if (selectedModel === 'gemini') {
      log('Using Gemini model via dedicated GeminiSocketService');
      if (geminiSocketService.sendMessage(currentPrompt)) {
        log('Message sent to Gemini via dedicated socket');
      } else {
        log('Failed to send message to Gemini - dedicated socket not connected');
        addSystemMessage('Error: Could not send message - Gemini service not connected');
        isProcessing = false;
      }
    } else {
      log('Using Claude model');
      try {
        log('Sending request to generate-reward API');
        const res = await fetch(`${API_URL}/generate-reward`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            prompt: currentPrompt,
            sessionId: $chatStore.sessionId
          })
        });

        const data = await res.json();
        log('Received response from generate-reward API', data);
        
        if (data.error) {
          throw new Error(data.error);
        }

        // Update the Claude conversation from the API response
        claudeConversation = data.conversation;
        
        // Also update chatStore for maintaining state
        chatStore.update(store => ({
          ...store,
          sessionId: data.sessionId,
          response: data.reward_config,
          conversation: data.conversation
        }));
        log('Updated chat store with response');

        try {
          log('Parsing reward configuration');
          const rewardConfig = JSON.parse(data.reward_config);
          
          if (rewardConfig.rewards && Array.isArray(rewardConfig.rewards)) {
            log('Valid rewards array found, processing rewards');
            const ws = websocketService.getSocket();
            if (ws?.readyState === WebSocket.OPEN) {
              log('Clearing active rewards via WebSocket');
              ws.send(JSON.stringify({
                type: "clear_active_rewards"
              }));
            }
            
            log('Cleaning rewards locally');
            rewardStore.cleanRewardsLocal();
            
            log('Adding new rewards', rewardConfig.rewards);
            rewardConfig.rewards.forEach((reward, index) => {
              rewardStore.addReward(reward.name, {
                id: reward.id || uuidv4(),
                name: reward.name,
                ...reward
              });
              
              if (rewardConfig.weights?.[index] !== undefined) {
                rewardStore.updateWeight(index, rewardConfig.weights[index]);
              }
            });
          } else {
            log('Invalid reward configuration format');
          }
        } catch (e) {
          log('Error processing reward configuration', e);
        }

        setTimeout(() => {
          chatContainer?.scrollTo({
            top: chatContainer.scrollHeight,
            behavior: 'smooth'
          });
          log('Scrolled to bottom after receiving Claude response');
        }, 100);

      } catch (error) {
        log('Error in API call', error);
        chatStore.update(store => ({
          ...store,
          response: `Error: ${error.message}`
        }));
      } finally {
        isProcessing = false;
        log('Processing completed');
      }
    }
  }

  function handleKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  async function clearChat() {
    log('Clearing chat');
    try {
      if (selectedModel === 'gemini') {
        log('Sending clear conversation request for Gemini');
        const ws = websocketService.getSocket();
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: "gemini_clear_conversation",
            client_id: webrtcService.clientId
          }));
        }
        
        // Clear Gemini conversation
        geminiConversation = [];
      } else {
        // For Claude, also need to clear on the server
        log('Sending clear-chat API request');
        const res = await fetch(`${API_URL}/clear-chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ sessionId: $chatStore.sessionId })
        });

        if (!res.ok) throw new Error('Failed to clear chat');
        log('Clear chat API request successful');
        
        // Clear Claude conversation
        claudeConversation = [];
        
        // Also update the chatStore
        chatStore.update(store => ({
          ...store,
          conversation: [],
          response: ''
        }));
      }
      
      log('Cleared local chat store');
    } catch (error) {
      log('Error clearing chat', error);
    }
    
    stopAutoCapture();
  }

  // Implement a direct test function for the "Check" button
  function testFlaskConnection() {
    if (flaskSocket && flaskSocket.connected) {
      log('FLASK SOCKET.IO TEST - SENDING gemini_connect');
      flaskSocket.emit('gemini_connect');
    } else {
      log('FLASK SOCKET.IO TEST - NOT CONNECTED');
    }
  }

  function switchModel(model) {
    if (model === selectedModel) return;
    
    log(`Switching model from ${selectedModel} to ${model}`);
    
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

<style>
  /* Fade-out animation for the snapshot status indicator */
  .animate-fade-out {
    animation: fadeOut 3s;
  }

  @keyframes fadeOut {
    0% { opacity: 1; }
    70% { opacity: 1; }
    100% { opacity: 0; }
  }
</style>

<div class="flex flex-col h-[600px]">
  <div class="flex justify-between items-center p-2 border-b">
    <div class="flex items-center space-x-2">
      <span class="text-sm text-gray-600">Model:</span>
      <div class="flex rounded-md overflow-hidden border">
        <button 
          class="px-3 py-1.5 text-sm {selectedModel === 'claude' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}" 
          on:click={() => switchModel('claude')}
        >
          Claude
        </button>
        <button 
          class="px-3 py-1.5 text-sm {selectedModel === 'gemini' ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}" 
          on:click={() => switchModel('gemini')}
        >
          Gemini Vision
        </button>
      </div>
    </div>
    
    <div class="flex items-center space-x-2">
      {#if selectedModel === 'gemini'}
        <button
          disabled={!isGeminiConnected}
          class="flex items-center px-2 py-1 text-sm rounded {autoCapture ? 'bg-red-500 text-white hover:bg-red-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} disabled:opacity-50 disabled:cursor-not-allowed"
          on:click={() => {
            log(`Auto-capture button clicked. Current state: ${autoCapture}, Connection: ${isGeminiConnected}`);
            toggleAutoCapture();
          }}
          title={autoCapture ? "Stop auto-capture" : "Start auto-capture"}
        >
          {#if autoCapture}
            <svg class="w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Stop Capture
          {:else}
            <svg class="w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Auto Capture
          {/if}
        </button>
        
        <button
          disabled={!isGeminiConnected}
          class="flex items-center px-2 py-1 text-sm rounded bg-purple-100 text-purple-700 hover:bg-purple-200 disabled:opacity-50 disabled:cursor-not-allowed"
          on:click={() => {
            log('Snapshot button clicked. Connection:', isGeminiConnected);
            captureFrame();
          }}
          title="Send current frame to Gemini"
        >
          <svg class="w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Snapshot
        </button>
        
        <!-- Snapshot status indicator that appears when a snapshot is sent -->
        {#if lastSnapshotStatus.timestamp > 0 && Date.now() - lastSnapshotStatus.timestamp < 3000}
          <div class="flex items-center animate-fade-out" 
               title={lastSnapshotStatus.success ? "Snapshot sent successfully" : "Failed to send snapshot"}>
            {#if lastSnapshotStatus.success}
              <div class="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded-full flex items-center">
                <svg class="w-3.5 h-3.5 mr-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                <span>Sent</span>
              </div>
            {:else}
              <div class="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded-full flex items-center">
                <svg class="w-3.5 h-3.5 mr-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
                <span>Failed</span>
              </div>
            {/if}
          </div>
        {/if}
        
        <!-- Debug button for connection -->
        <button
          class="flex items-center px-2 py-1 text-sm rounded bg-green-100 text-green-700 hover:bg-green-200"
          on:click={() => {
            log('Manual Flask connection test triggered');
            testFlaskConnection();
          }}
          title="Test Flask connection"
        >
          <svg class="w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
          </svg>
          Check
        </button>
        
        <div class="flex items-center space-x-1">
          <div class={`w-2 h-2 rounded-full ${isGeminiConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <span class="text-xs text-gray-500">{isGeminiConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
      {/if}
      
      <button
        on:click={clearChat}
        class="text-sm px-3 py-1 text-gray-600 hover:text-gray-800 flex items-center gap-1 rounded hover:bg-gray-200"
      >
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
        Clear Chat
      </button>
    </div>
  </div>

  <div 
    bind:this={chatContainer}
    class="flex-1 overflow-y-auto p-4 space-y-4"
  >
    {#if (selectedModel === 'claude' ? claudeConversation.length === 0 : geminiConversation.length === 0)}
      <div class="flex items-center justify-center h-full">
        <div class="text-center text-gray-500 dark:text-gray-400 p-8">
          <h3 class="text-lg font-medium mb-2">Start a conversation</h3>
          {#if selectedModel === 'gemini'}
            <p>Use Gemini Vision to analyze the video feed in real-time.</p>
            <p class="text-sm mt-2">Try sending a snapshot or enabling auto-capture.</p>
          {:else}
            <p>Describe the behavior you'd like to create.</p>
            <p class="text-sm mt-2">For example: "Make the character walk forward while waving"</p>
          {/if}
        </div>
      </div>
    {:else}
      {#each selectedModel === 'claude' ? claudeConversation : geminiConversation as message}
        <div class="flex gap-2 {message.role === 'assistant' ? 'bg-gray-50' : message.role === 'system' ? 'bg-gray-100' : ''} p-4 rounded-lg">
          <div class="w-8 h-8 rounded-full flex items-center justify-center shrink-0 
                      {message.role === 'assistant' 
                        ? selectedModel === 'gemini' ? 'bg-purple-600' : 'bg-blue-600' 
                        : message.role === 'system' ? 'bg-gray-400' : 'bg-gray-600'}">
            {#if message.role === 'assistant'}
              <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                      d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            {:else if message.role === 'system'}
              <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            {:else}
              <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                      d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            {/if}
          </div>

          <div class="flex-1 space-y-2">
            <div class="font-medium text-sm text-gray-600">
              {#if message.role === 'user'}
                You
              {:else if message.role === 'assistant'}
                {selectedModel === 'gemini' ? 'Gemini' : 'Claude'}
              {:else}
                System
              {/if}
            </div>
            
            {#if message.role === 'user'}
              <div class="text-gray-800">
                {message.content}
              </div>
            {:else if message.role === 'system'}
              <div class="text-gray-600 text-sm italic">
                {message.content}
              </div>
            {:else}
              <div class="space-y-2">
                {#if selectedModel === 'claude'}
                  <div class="text-gray-800">
                    Generated behavior configuration:
                  </div>
                  <div class="bg-gray-100 rounded p-3 font-mono text-sm">
                    {message.content}
                  </div>
                {:else}
                  <div class="text-gray-800">
                    {message.content}
                  </div>
                {/if}
              </div>
            {/if}
          </div>
        </div>
      {/each}
    {/if}
  </div>

  <div class="border-t p-4">
    <div class="max-w-4xl mx-auto">
      <form 
        on:submit|preventDefault={handleSubmit}
        class="flex gap-4 items-end"
      >
        <div class="flex-1">
          <textarea
            id="prompt"
            bind:value={prompt}
            rows="3"
            on:keydown={handleKeydown}
            placeholder={selectedModel === 'gemini' 
              ? "Ask Gemini about what's happening in the video..." 
              : "Describe the desired behavior (e.g., 'Walk forward while waving both hands')"}
            class="block w-full rounded-lg border-0 py-2 px-3 text-gray-900 bg-white ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-blue-600 resize-none shadow-lg"
          ></textarea>
        </div>
        
        <button
          type="submit"
          disabled={isProcessing}
          class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed flex items-center gap-2 h-[42px] shadow-lg"
        >
          {#if isProcessing}
            <svg class="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          {:else}
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          {/if}
        </button>
      </form>
    </div>
  </div>
</div> 