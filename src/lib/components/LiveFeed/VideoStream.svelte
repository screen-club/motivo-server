<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { websocketService, computingStatus } from '../../services/websocket';
  import { webrtcService, isLoading, hasStream, currentQuality, qualityOptions } from '../../services/webrtc';
  
  const dispatch = createEventDispatcher();
  
  export let showControls = true;
  export let showLoadingOverlay = true;
  export let isPiPMode = false;
  export let isLargePiP = false;
  
  // References
  let videoElement;
  let videoContainer;
  let isConnected = false;
  let isFullscreen = false;
  let isRecording = false;
  let recordingStatus = null;
  
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
  
  // Video recording functionality
  function toggleRecording() {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }
  
  function startRecording() {
    if (!isConnected) return;
    
    const message = {
      type: "start_video_recording",
      timestamp: new Date().toISOString()
    };
    
    websocketService.send(message);
    isRecording = true;
    
    // Add WebSocket message handler for recording status
    const handleRecordingMessage = (data) => {
      if (data.type === "video_recording_status") {
        recordingStatus = data;
        
        // If the recording was stopped (either by user or auto-stop)
        if (data.status === "stopped") {
          isRecording = false;
          
          // Show notification with download link
          if (data.path) {
            const notification = document.createElement('div');
            notification.className = 'fixed top-4 right-4 bg-green-500 text-white p-4 rounded shadow-lg z-50';
            
            // Create download link if available
            // Get the API base URL for potential URL fixing
            const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:5002';
            
            // Create a more reliable download URL using the motivo-videos route
            const filename = data.filename || 'recording.mp4';
            const motivoUrl = `${apiBaseUrl}/motivo-videos/${filename}`;
            console.log(`Using reliable motivo URL: ${motivoUrl}`);
            
            // Keep the original URL as backup
            let downloadUrl = data.downloadUrl;
            if (downloadUrl && !downloadUrl.startsWith('http')) {
              downloadUrl = downloadUrl.startsWith('/') 
                ? apiBaseUrl + downloadUrl 
                : apiBaseUrl + '/' + downloadUrl;
              console.log(`Original URL (backup): ${downloadUrl}`);
            }
            
            // Prefer the motivo URL for more reliable access
            downloadUrl = motivoUrl;
            
            const downloadLink = downloadUrl 
              ? `<a href="${downloadUrl}" class="inline-flex items-center mt-2 px-3 py-1 bg-white text-green-700 rounded-full text-xs font-medium hover:bg-gray-100" download="${data.filename || 'recording.mp4'}" target="_blank">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download Video
                </a>`
              : '';
            
            notification.innerHTML = `
              <div>
                <div class="flex items-center">
                  <svg class="w-6 h-6 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                  </svg>
                  <div class="flex-grow">
                    <p class="font-bold">Video saved!</p>
                    <p class="text-sm truncate max-w-[200px]">${data.filename || 'recording.mp4'}</p>
                  </div>
                  <button data-close-button class="ml-4 text-white hover:text-gray-200 flex-shrink-0">×</button>
                </div>
                ${downloadLink ? `
                  <div class="mt-2 animate-pulse">
                    ${downloadLink}
                    <p class="text-xs mt-1 text-white/80">Click to download your video</p>
                    <p class="text-xs text-white/60">${downloadUrl}</p>
                  </div>
                ` : `<p class="text-xs mt-1 text-white/80">Video saved to server</p>`}
              </div>
            `;
            document.body.appendChild(notification);
            
            const closeButton = notification.querySelector('[data-close-button]');
            
            // Keep notification longer since it has the download link
            const timeout = setTimeout(() => {
              if (notification.parentElement) {
                notification.remove();
              }
            }, 30000); // 30 seconds - extended to give users more time to download
            
            // Add event listener to the close button
            if (closeButton) {
              closeButton.addEventListener('click', () => {
                console.log('Close button clicked. Attempting to remove notification:', notification);
                clearTimeout(timeout);
                if (notification.parentElement) {
                  notification.remove();
                  console.log('Notification removed from DOM.');
                } else {
                  console.warn('Notification parentElement not found, likely already removed or detached.');
                }
              });
            }
          }
        }
      }
    };
    
    // Add the handler
    recordingMessageHandlerId = websocketService.addMessageHandler(handleRecordingMessage);
  }
  
  function stopRecording() {
    if (!isConnected) return;
    
    const message = {
      type: "stop_video_recording",
      timestamp: new Date().toISOString()
    };
    
    websocketService.send(message);
    // Don't set isRecording to false here - wait for confirmation from server
  }
  
  let recordingMessageHandlerId = null;
  
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
      
      // Clean up recording message handler
      if (recordingMessageHandlerId) {
        websocketService.removeMessageHandler(recordingMessageHandlerId);
      }
      
      // Remove fullscreen change event listeners
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
      document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
      document.removeEventListener('mozfullscreenchange', handleFullscreenChange);
      document.removeEventListener('MSFullscreenChange', handleFullscreenChange);
    });
  });
</script>

<div class="{containerWidth} mx-auto">
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
      class="w-full h-auto object-contain"
      style="image-rendering: auto; max-height: {isFullscreen ? '100vh' : containerMaxHeight};"
    ></video>

    <!-- Overlay Controls -->
    {#if showControls}
      <div class="absolute bottom-0 left-0 right-0 p-2 bg-black/50 backdrop-blur-sm z-20">
        <div class="{containerWidth} mx-auto flex items-center justify-between text-white">
          <div class="flex gap-2 ml-auto">
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
              class="text-xs bg-gray-800 hover:bg-gray-700 p-1 rounded flex items-center"
              on:click={() => dispatch('togglePip')}
              title={isLargePiP ? "Shrink video" : "Expand video"}
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                {#if isLargePiP}
                  <!-- Minus Icon -->
                  <path stroke-linecap="round" stroke-linejoin="round" d="M20 12H4" />
                {:else}
                  <!-- Plus Icon -->
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m6-6H6" />
                {/if}
              </svg>
            </button>
            
            <button 
              class="text-xs bg-gray-800 hover:bg-gray-700 p-1 rounded flex items-center"
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
            </button>
            
            <button 
              class="text-xs {isRecording ? 'bg-red-500 hover:bg-red-600' : 'bg-green-500 hover:bg-green-600'} px-2 py-1 rounded flex items-center"
              on:click={toggleRecording}
              title={isRecording ? "Stop recording" : "Start recording"}
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                {#if isRecording}
                  <!-- Stop icon -->
                  <rect x="6" y="6" width="12" height="12" stroke-width="2" />
                {:else}
                  <!-- Record icon -->
                  <circle cx="12" cy="12" r="6" fill="currentColor" stroke="none" />
                {/if}
              </svg>
              {isRecording ? "Stop" : "Record"}
            </button>
          </div>
        </div>
      </div>
    {/if}
  </div>
</div>