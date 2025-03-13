<script>
  import { webrtcService, connectionLogs, currentQuality } from '../../services/webrtc';
</script>

<div class="mt-4 p-4 bg-gray-900 rounded-lg text-gray-200 text-sm overflow-hidden">
  <div class="flex justify-between items-center mb-2">
    <h3 class="font-semibold">WebRTC Debug Information</h3>
    <div class="flex gap-2">
      <span class="text-xs text-gray-400 font-mono">
        Quality: {$currentQuality}
      </span>
      
      <!-- Direct WebSocket test button -->
      <button 
        class="bg-green-500 hover:bg-green-600 px-2 py-1 rounded text-xs mr-2"
        on:click={() => {
          try {
            webrtcService.logger.log('Attempting direct WebSocket connection test...');
            const wsUrl = import.meta.env.VITE_WS_URL;
            webrtcService.logger.log(`Direct connection to: ${wsUrl}`);
            
            const testSocket = new WebSocket(wsUrl);
            
            testSocket.onopen = () => {
              webrtcService.logger.log('Direct WebSocket connection successful!');
              testSocket.send(JSON.stringify({
                type: 'ping',
                timestamp: new Date().toISOString(),
                test: true
              }));
              
              setTimeout(() => {
                if (testSocket.readyState === WebSocket.OPEN) {
                  testSocket.close();
                  webrtcService.logger.log('Direct test connection closed');
                }
              }, 5000);
            };
            
            testSocket.onmessage = (event) => {
              webrtcService.logger.log(`Direct test received: ${event.data.substring(0, 50)}...`);
            };
            
            testSocket.onerror = (event) => {
              webrtcService.logger.log(`Direct test error: ${event}`);
            };
            
            testSocket.onclose = (event) => {
              webrtcService.logger.log(`Direct test closed: ${event.code} ${event.reason}`);
            };
            
            // Set timeout for connection
            setTimeout(() => {
              if (testSocket.readyState === WebSocket.CONNECTING) {
                webrtcService.logger.log('Direct test connection timed out');
                testSocket.close();
              }
            }, 10000);
          } catch (error) {
            webrtcService.logger.error(`Error in direct test: ${error.message}`);
          }
        }}
      >
        Direct WS Test
      </button>
      
      <button 
        class="bg-blue-500 hover:bg-blue-600 px-2 py-1 rounded text-xs"
        on:click={() => webrtcService.restartConnection()}
      >
        Restart Connection
      </button>
    </div>
  </div>
  
  <div class="space-y-1 h-[200px] overflow-y-auto">
    {#each $connectionLogs as log}
      <div class="font-mono text-xs {log.level === 'error' ? 'text-red-400' : log.level === 'warning' ? 'text-yellow-400' : 'text-gray-300'}">
        <span class="text-gray-400">{log.timestamp}</span>: {log.message}
      </div>
    {/each}
  </div>
  
  <div class="mt-2 text-xs text-gray-400">
    Connection ID: {webrtcService.clientId || 'unknown'}
  </div>
</div>