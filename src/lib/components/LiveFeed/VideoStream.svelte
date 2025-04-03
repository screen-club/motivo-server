<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { websocketService, computingStatus } from '../../services/websocket';
  import { webrtcService, isLoading, hasStream, currentQuality, qualityOptions } from '../../services/webrtc';
  
  const dispatch = createEventDispatcher();
  
  export let showControls = true;
  export let showLoadingOverlay = true;
  
  // References
  let videoElement;
  let videoContainer;
  let isConnected = false;
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
      case 'high': return '720px';
      default: return '480px';
    }
  }
  
  // Change video quality
  function setVideoQuality(quality) {
    webrtcService.setVideoQuality(quality);
  }
  
  // Fullscreen handling
  function toggleFullscreen() {
    if (!videoContainer) return;
    
    if (!isFullscreen) {
      if (videoContainer.requestFullscreen) {
        videoContainer.requestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
  }
  
  // Listen for fullscreen change events
  function handleFullscreenChange() {
    isFullscreen = !!document.fullscreenElement;
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
    dispatch('restart');
  }
  
  onMount(() => {
    // Set video element reference
    webrtcService.setVideoElement(videoElement);
    
    // Add ready state change listener
    const cleanupListener = websocketService.onReadyStateChange(handleReadyState);
    
    // Check initial connection state
    isConnected = websocketService.isConnected();
    if (isConnected) {
      webrtcService.initWebRTC();
    }
    
    // Add fullscreen change event listeners
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);
    
    // Cleanup on destroy
    onDestroy(() => {
      if (cleanupListener) cleanupListener();
      
      // Remove fullscreen change event listeners
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
      document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
      document.removeEventListener('mozfullscreenchange', handleFullscreenChange);
      document.removeEventListener('MSFullscreenChange', handleFullscreenChange);
    });
  });
</script>

<div class={containerWidth + " mx-auto"}>
  <!-- Video Container -->
  <div 
    bind:this={videoContainer} 
    class="relative rounded-xl overflow-hidden bg-white shadow-lg border border-gray-200"
  >
    {#if showLoadingOverlay && (!isConnected || $isLoading)}
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

    <!-- Overlay Controls -->
    {#if showControls}
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
              class="text-xs bg-blue-500 hover:bg-blue-600 px-2 py-1 rounded"
              on:click={restartConnection}
              title="Restart connection"
            >
              Restart
            </button>
          </div>
        </div>
      </div>
    {/if}
  </div>
</div>