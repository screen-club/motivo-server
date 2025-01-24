<script>
  export let socket;
  
  let isRecording = false;
  let isConnected = false;
  
  $: {
    // Update connection status whenever socket changes
    isConnected = socket?.readyState === WebSocket.OPEN;
    console.log('Socket state:', socket?.readyState, 'Connected:', isConnected);
  }

  function toggleRecording() {
    if (!isConnected) {
      console.error('WebSocket not connected');
      return;
    }

    const message = {
      type: isRecording ? 'stop_recording' : 'start_recording',
      timestamp: new Date().toISOString()
    };
    
    console.log('Sending recording message:', message);
    socket.send(JSON.stringify(message));
  }

  // Add message listener when socket is available
  $: if (socket) {
    socket.addEventListener('message', (event) => {
      console.log('RecordButton received:', event.data);
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'recording_status') {
          console.log('Recording status updated:', data.status);
          isRecording = data.status === 'started';
        }
      } catch (error) {
        console.error('Error parsing message:', error);
      }
    });
  }
</script>

<button
  on:click={toggleRecording}
  class="flex items-center gap-2 px-4 py-2 rounded-full font-medium transition-colors {isRecording 
    ? 'bg-red-500 hover:bg-red-600 text-white' 
    : 'bg-green-500 hover:bg-green-600 text-white'}"
  disabled={!isConnected}
>
  <div class="w-3 h-3 rounded-full {isRecording ? 'animate-pulse bg-white' : 'bg-white'}"></div>
  {isRecording ? 'Stop Recording' : 'Start Recording'}
</button>

<style>
  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style> 