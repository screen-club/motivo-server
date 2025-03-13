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
  let lastSnapshotStatus = $state({ success: false, timestamp: 0 });
  let claudeConversation = $state([]);
  let geminiConversation = $state([]);
  let structuredResponse = $state(null);

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
      }
    });
    
    // Set up Gemini client
    geminiClient.connect(API_URL);
    
    // Check Gemini connection status
    const checkConnectionInterval = setInterval(() => {
      geminiClient.checkConnection();
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

  // Helper function to safely render markdown
  function renderMarkdown(content, isComplete) {
    try {
      // Use a special class when the message is still streaming
      const className = isComplete ? 'markdown-complete' : 'markdown-streaming';
      return `<div class="${className}">${md.render(content)}</div>`;
    } catch (error) {
      console.error('Error rendering markdown', error);
      return content; // Fallback to plain text if rendering fails
    }
  }

  function toggleAutoCapture() {
    if (autoCapture) {
      stopAutoCapture();
    } else {
      startAutoCapture();
    }
  }

  function startAutoCapture() {
    if (!isGeminiConnected) {
      return;
    }
    
    autoCapture = true;
    captureInterval = setInterval(() => {
      captureFrame();
    }, 2000);
    
    addSystemMessage('Auto-capture started (1 snapshot every 2 seconds)');
  }

  function stopAutoCapture() {
    if (captureInterval) {
      clearInterval(captureInterval);
      captureInterval = null;
    }
    autoCapture = false;
    
    if (lastCaptureTime > 0) {
      addSystemMessage('Auto-capture stopped');
    }
  }

  function captureFrame() {
    if (geminiClient.captureFrame()) {
      lastCaptureTime = Date.now();
      lastSnapshotStatus = { success: true, timestamp: Date.now() };
    } else {
      addSystemMessage('Error: Could not capture frame - service not connected');
      lastSnapshotStatus = { success: false, timestamp: Date.now() };
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
      if (!geminiClient.sendMessage(currentPrompt)) {
        isProcessing = false;
      }
    } else {
      // Claude
      const result = await claudeClient.sendMessage(API_URL, currentPrompt, $chatStore.sessionId);
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
    {lastSnapshotStatus}
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
    onSubmit={handleSubmit}
  />
</div>