<script>
  import { onMount } from 'svelte';
  import { isLoading } from '../../services/webrtc';
  import { websocketService, computingStatus } from '../../services/websocket';
  import VideoStream from './VideoStream.svelte';
  import StatusBar from '../StatusBar.svelte';
  
  let troubleshootMode = $state(false);
  let isConnected = $state(false);
  

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
  <VideoStream />
  
  <!-- Status Bar -->
  <StatusBar 
    isLoading={$isLoading}
    {isConnected}
  />
  
 
  
</div>