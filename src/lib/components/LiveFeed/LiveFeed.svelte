<script>
  import { onMount } from 'svelte';
  import { isLoading } from '../../services/webrtc';
  import { websocketService, computingStatus } from '../../services/websocket';
  import VideoStream from './VideoStream.svelte';
  import ConnectionDebug from './ConnectionDebug.svelte';
  import StatusBar from '../StatusBar.svelte';
  
  let troubleshootMode = $state(false);
  let isConnected = $state(false);
  
  function toggleTroubleshootMode() {
    troubleshootMode = !troubleshootMode;
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
  <VideoStream />
  
  <!-- Status Bar -->
  <StatusBar 
    isLoading={$isLoading}
    {isConnected}
  />
  
  <!-- Debug Tools -->
  <div class="mt-2 flex justify-end">
    <button 
      class="text-xs bg-purple-500 hover:bg-purple-600 px-2 py-1 rounded text-white"
      onclick={toggleTroubleshootMode}
    >
      {troubleshootMode ? 'Hide Debug' : 'Show Debug'}
    </button>
  </div>
  
  <!-- Troubleshooting Panel -->
  {#if troubleshootMode}
    <ConnectionDebug />
  {/if}
</div>