<script>
  import { onMount, createEventDispatcher } from 'svelte';
  import { isLoading, hasStream } from '../../services/webrtc';
  import { websocketService, computingStatus } from '../../services/websocket';
  import VideoStream from './VideoStream.svelte';
  
  let { isPiPMode = false, isLargePiP = false } = $props(); // Accept individual states
  const dispatch = createEventDispatcher(); // Create dispatcher instance
  
  let troubleshootMode = $state(false);
  let isConnected = $state(false);
  
  function forwardTogglePip() {
    dispatch('togglePip'); // Re-dispatch the event
  }

  onMount(() => {
    // Check initial connection state
    isConnected = websocketService.getSocket()?.readyState === WebSocket.OPEN;
    
    // Add ready state change listener
    const cleanupListener = websocketService.onReadyStateChange((connected) => {
      isConnected = connected;
    });
    
    return cleanupListener;
  });
</script>

<div class="w-full">
  <!-- Video Stream -->
  <VideoStream {isPiPMode} {isLargePiP} on:togglePip={forwardTogglePip} />
  
  <!-- Compact Status Indicators -->
  <div class="flex items-center gap-4 px-2 py-1 text-xs text-gray-600 border-t border-gray-200 bg-gray-50 rounded-b-xl">
    <div class="flex items-center gap-1.5">
      <span 
        class="w-2 h-2 rounded-full"
        class:bg-green-500={isConnected}
        class:bg-red-500={!isConnected}
      ></span>
      WebSocket
    </div>
    <div class="flex items-center gap-1.5">
      <span 
        class="w-2 h-2 rounded-full"
        class:bg-green-500={$hasStream}
        class:bg-yellow-400={!$hasStream && $isLoading}
        class:bg-red-500={!$hasStream && !$isLoading}
      ></span>
      Video
    </div>
  </div>
</div>