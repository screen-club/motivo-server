<script>
  import { onMount, onDestroy } from 'svelte';
  import { websocketService, computingStatus } from '../services/websocketService';
  import { webrtcService, isLoading, hasStream, connectionLogs, currentQuality, qualityOptions } from '../services/webrtcService';
  import StatusBar from './StatusBar.svelte';
  import RecordButton from './RecordButton.svelte';
  
  // Reactive states
  let videoElement;
  let videoContainer;
  let isConnected = false;
  let troubleshootMode = false;
  let isFullscreen = false;
  
  // Container sizing based on quality
  $: containerWidth = getContainerWidth($currentQuality);
  $: containerMaxHeight = getContainerMaxHeight($currentQuality);
  
  function getContainerWidth(quality) {
    switch(quality) {
      case 'high': return 'max-w-3xl';
      default: return 'max-w-2xl';
    }
  }
  
  function getContainerMaxHeight(quality) {
    switch(quality) {
      case 'high': return '720px'; // Limiting height for better display
      default: return '480px';
    }
  }
  
  function toggleTroubleshootMode() {
    troubleshootMode = !troubleshootMode;
  }

  // WebSocket status tracking
  let cleanupListener;

  // Change video quality
  function setVideoQuality(quality) {
    webrtcService.setVideoQuality(quality);
  }

  // Fullscreen handling
  function toggleFullscreen() {
    if (!videoContainer) return;
    
    if (!isFullscreen) {
      // Enter fullscreen
      if (videoContainer.requestFullscreen) {
        videoContainer.requestFullscreen();
      }
    } else {
      // Exit fullscreen
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
  }
  
  // Listen for fullscreen change events
  function handleFullscreenChange() {
    isFullscreen = !!document.fullscreenElement;
    webrtcService.addLog(`Fullscreen mode: ${isFullscreen ? 'enabled' : 'disabled'}`);
  }

  function handleReadyState(ready) {
    isConnected = ready;
    webrtcService.handleWebSocketStateChange(ready);
    
    if (!ready) {
      $computingStatus = false;
    }
  }
  
  function restartConnection() {
    webrtcService.restartConnection();
  }
  
  onMount(() => {
    webrtcService.addLog('Component mounted');
    
    // Set video element reference
    webrtcService.setVideoElement(videoElement);
    
    // Add ready state change listener
    cleanupListener = websocketService.onReadyStateChange(handleReadyState);
    
    // Check initial connection state
    isConnected = websocketService.getSocket()?.readyState === WebSocket.OPEN;
    webrtcService.addLog('Initial WebSocket state: ' + (isConnected ? 'connected' : 'disconnected'));
    if (isConnected) {
      webrtcService.initWebRTC();
    }
    
    // Add fullscreen change event listeners
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);
  });
  
  onDestroy(() => {
    webrtcService.addLog('Component unmounting');
    if (cleanupListener) cleanupListener();
    
    // Clean up WebRTC
    webrtcService.cleanup();
    
    // Remove fullscreen change event listeners
    document.removeEventListener('fullscreenchange', handleFullscreenChange);
    document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.removeEventListener('mozfullscreenchange', handleFullscreenChange);
    document.removeEventListener('MSFullscreenChange', handleFullscreenChange);
  });
</script>

<div class={containerWidth + " mx-auto"}>
  <!-- Video Container -->
  <div bind:this={videoContainer} class="relative rounded-xl overflow-hidden bg-white shadow-lg border border-gray-200">
    {#if !isConnected || $isLoading}
      <div class="absolute inset-0 flex items-center justify-center bg-gray-50/80 backdrop-blur-sm z-10">
        <div class="flex flex-col items-center gap-2">
          <div class="animate-spin rounded-full h-12 w-12 border-4 border-purple-500 border-t-transparent"></div>
          <span class="text-sm text-gray-600">
            {!isConnected ? 'Connecting...' : 'Setting up video stream...'}
          </span>
        </div>
      </div>
    {/if}
    
    <!-- WebRTC Video Stream -->
    <video
      bind:this={videoElement}
      autoplay
      playsinline
      muted
      class="w-full h-auto object-contain bg-black"
      style="image-rendering: auto; max-height: {isFullscreen ? '100vh' : containerMaxHeight};"
    ></video>

    <!-- Updated Overlay Controls -->
    <div class="absolute bottom-0 left-0 right-0 p-2 bg-black/50 backdrop-blur-sm">
      <div class="flex items-center justify-between text-white">
        <span class="text-sm font-medium">
          {#if !isConnected}
            <span class="text-red-400">Disconnected</span>
          {:else if $computingStatus}
            <span class="text-yellow-400">Processing...</span>
          {:else}
            <span class="text-green-400">Ready</span>
          {/if}
        </span>
        <div class="flex gap-2">
          <select 
            class="text-xs bg-gray-800 border border-gray-700 rounded px-1 py-0.5 text-white"
            value={$currentQuality}
            on:change={(e) => setVideoQuality(e.currentTarget.value)}
          >
            {#each qualityOptions as option}
              <option value={option.id} class={option.recommended ? 'font-semibold' : ''}>
                {option.label}
              </option>
            {/each}
          </select>
          <button 
            class="text-xs bg-gray-800 hover:bg-gray-700 px-2 py-1 rounded flex items-center"
            on:click={toggleFullscreen}
            title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {#if isFullscreen}
                <!-- Exit fullscreen icon -->
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              {:else}
                <!-- Enter fullscreen icon -->
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
              {/if}
            </svg>
            <span class="ml-1">{isFullscreen ? "Exit" : "Fullscreen"}</span>
          </button>
          <button 
            class="text-xs bg-purple-500 hover:bg-purple-600 px-2 py-1 rounded"
            on:click={toggleTroubleshootMode}
          >
            {troubleshootMode ? 'Hide Debug' : 'Debug'}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Status Bar -->
  <StatusBar 
    isLoading={$isLoading}
    {isConnected}
  />
  
  <!-- Troubleshooting Panel -->
  {#if troubleshootMode}
    <div class="mt-4 p-4 bg-gray-900 rounded-lg text-gray-200 text-sm overflow-hidden">
      <div class="flex justify-between items-center mb-2">
        <h3 class="font-semibold">WebRTC Debug Information</h3>
        <div class="flex gap-2">
          <span class="text-xs text-gray-400 font-mono">
            Quality: {$currentQuality}
          </span>
          
          <!-- Add direct WebSocket test button -->
          <button 
            class="bg-green-500 hover:bg-green-600 px-2 py-1 rounded text-xs mr-2"
            on:click={() => {
              try {
                webrtcService.addLog('Attempting direct WebSocket connection test...');
                const wsUrl = import.meta.env.VITE_WS_URL;
                webrtcService.addLog(`Direct connection to: ${wsUrl}`);
                
                const testSocket = new WebSocket(wsUrl);
                
                testSocket.onopen = () => {
                  webrtcService.addLog('Direct WebSocket connection successful!');
                  testSocket.send(JSON.stringify({
                    type: 'ping',
                    timestamp: new Date().toISOString(),
                    test: true
                  }));
                  
                  setTimeout(() => {
                    if (testSocket.readyState === WebSocket.OPEN) {
                      testSocket.close();
                      webrtcService.addLog('Direct test connection closed');
                    }
                  }, 5000);
                };
                
                testSocket.onmessage = (event) => {
                  webrtcService.addLog(`Direct test received: ${event.data.substring(0, 50)}...`);
                };
                
                testSocket.onerror = (event) => {
                  webrtcService.addLog(`Direct test error: ${event}`);
                };
                
                testSocket.onclose = (event) => {
                  webrtcService.addLog(`Direct test closed: ${event.code} ${event.reason}`);
                };
                
                // Set timeout for connection
                setTimeout(() => {
                  if (testSocket.readyState === WebSocket.CONNECTING) {
                    webrtcService.addLog('Direct test connection timed out');
                    testSocket.close();
                  }
                }, 10000);
              } catch (error) {
                webrtcService.addLog(`Error in direct test: ${error.message}`);
              }
            }}
          >
            Direct WS Test
          </button>
          
          <button 
            class="bg-blue-500 hover:bg-blue-600 px-2 py-1 rounded text-xs"
            on:click={restartConnection}
          >
            Restart Connection
          </button>
        </div>
      </div>
      <div class="space-y-1 h-[200px] overflow-y-auto">
        {#each $connectionLogs as log}
          <div class="font-mono text-xs">
            <span class="text-gray-400">{log.timestamp}</span>: {log.message}
          </div>
        {/each}
      </div>
      <div class="mt-2 text-xs text-gray-400">
        Connection ID: {webrtcService.clientId}
      </div>
    </div>
  {/if}
</div> 