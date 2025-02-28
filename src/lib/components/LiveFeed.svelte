<script>
  import { onMount, onDestroy } from 'svelte';
  import { websocketService, computingStatus } from '../services/websocketService';
  import StatusBar from './StatusBar.svelte';
  import RecordButton from './RecordButton.svelte';
  import { v4 as uuidv4 } from 'uuid';
  
  const apiUrl = import.meta.env.VITE_API_URL;
  const clientId = uuidv4(); // Unique ID for this client

  // test

  // Reactive states
  let videoElement;
  let videoContainer;
  let isLoading = true;
  let isConnected = false;
  let peerConnection = null;
  let dataChannel = null;
  let hasStream = false;
  let troubleshootMode = false;
  let connectionLogs = [];
  let maxLogEntries = 20;
  let isFullscreen = false;
  
  // Video quality settings
  let currentQuality = "medium"; // Default to medium quality (640x480)
  let qualityOptions = [
    { id: "medium", label: "Standard (640×480)", recommended: true },
    { id: "high", label: "High (1280×960)" }
  ];
  
  // Container sizing based on quality
  $: containerWidth = getContainerWidth(currentQuality);
  $: containerMaxHeight = getContainerMaxHeight(currentQuality);
  
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
  
  function addLog(message) {
    const timestamp = new Date().toLocaleTimeString();
    connectionLogs = [{timestamp, message}, ...connectionLogs.slice(0, maxLogEntries - 1)];
    console.log(`${timestamp}: ${message}`);
  }
  
  function toggleTroubleshootMode() {
    troubleshootMode = !troubleshootMode;
  }

  // WebSocket status tracking
  let cleanupMessageHandler;
  let cleanupListener;

  // Change video quality
  function setVideoQuality(quality) {
    if (quality === currentQuality) return;
    
    addLog(`Requesting video quality change to: ${quality}`);
    
    // Send quality change request to server
    websocketService.send({
      type: 'set_video_quality',
      quality: quality,
      client_id: clientId
    });
    
    currentQuality = quality;
    
    // Restart WebRTC to apply changes
    setTimeout(() => {
      initWebRTC();
    }, 500);
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
    
    addLog(`Fullscreen mode: ${isFullscreen ? 'enabled' : 'disabled'}`);
  }

  // Initialize WebRTC
  async function initWebRTC() {
    try {
      isLoading = true;
      addLog('Starting WebRTC initialization...');
      
      // Clean up any existing connection
      if (peerConnection) {
        addLog('Closing existing peer connection');
        peerConnection.close();
        peerConnection = null;
      }

      
      // Create a new RTCPeerConnection
      const configuration = { 
        iceServers: [
          // Use the custom COTURN server (same as backend)
          { urls: 'stun:51.159.163.145:3478' },
          {
            urls: 'turn:51.159.163.145:3478',
            username: 'admin',
            credential: 'password'
          },
          {
            urls: 'turn:51.159.163.145:3478?transport=tcp',
            username: 'admin',
            credential: 'password'
          }
        ] 
      };
      addLog('Creating peer connection with config: ' + JSON.stringify(configuration));
      
      peerConnection = new RTCPeerConnection(configuration);
      
      // Set up event handlers for the connection
      peerConnection.ontrack = (event) => {
        addLog('Track received: ' + event.streams?.length + ' streams');
        if (event.streams && event.streams[0]) {
          if (videoElement) {
            addLog('Setting video source to received stream');
            videoElement.srcObject = event.streams[0];
            
            // Basic video setup with minimal processing
            videoElement.play().catch(e => addLog('Video play error: ' + e.message));
            
            // Simple video settings - no enhancements, filters or effects
            // Let the browser render the raw frames as cleanly as possible
            videoElement.style.width = '100%';
            videoElement.style.imageRendering = 'auto';  // Default rendering
            videoElement.style.filter = 'none';          // No filters
            videoElement.style.transform = 'none';       // No transforms
            
            // Force the browser to handle this as a high-quality video
            videoElement.setAttribute('playsinline', 'true');
            videoElement.setAttribute('muted', 'true');
            
            hasStream = true;
            isLoading = false;
          } else {
            addLog('Video element not available');
          }
        }
      };
      
      peerConnection.onicecandidate = (event) => {
        if (event.candidate) {
          addLog('ICE candidate generated: ' + event.candidate.candidate.substring(0, 50) + '...');
          // Send the ICE candidate to the server - simplified to just what aiortc needs
          websocketService.send({
            type: 'ice_candidate',
            candidate: {
              sdpMid: event.candidate.sdpMid,
              sdpMLineIndex: event.candidate.sdpMLineIndex,
              candidate: event.candidate.candidate
            },
            client_id: clientId
          });
        } else {
          addLog('ICE candidate gathering complete');
        }
      };
      
      // Add more detailed connection state monitoring
      peerConnection.oniceconnectionstatechange = () => {
        addLog(`ICE connection state changed to: ${peerConnection.iceConnectionState}`);
        if (peerConnection.iceConnectionState === 'disconnected' || 
            peerConnection.iceConnectionState === 'failed' || 
            peerConnection.iceConnectionState === 'closed') {
          hasStream = false;
          isLoading = true;
          
          // Attempt to reconnect after a short delay
          setTimeout(() => {
            if (isConnected) {
              addLog('Attempting to reconnect WebRTC...');
              initWebRTC();
            }
          }, 2000);
        } else if (peerConnection.iceConnectionState === 'connected') {
          addLog('WebRTC connection established successfully');
        }
      };
      
      peerConnection.onsignalingstatechange = () => {
        addLog(`Signaling state changed to: ${peerConnection.signalingState}`);
      };
      
      peerConnection.onconnectionstatechange = () => {
        addLog(`Connection state changed to: ${peerConnection.connectionState}`);
        if (peerConnection.connectionState === 'connected') {
          addLog('WebRTC connection established!');
        }
      };
      
      // Create offer with improved quality settings
      addLog('Creating WebRTC offer with optimized codec settings...');
      
      // Set codec preferences based on quality
      let codecPreferences = {};
      
      if (currentQuality === 'high') {
        // For high quality, try to use better codecs with higher bitrates
        codecPreferences = {
          offerToReceiveVideo: true,
          offerToReceiveAudio: false,
          voiceActivityDetection: false,
        };
        
        // Try to set codec preferences if supported by the browser
        try {
          if (RTCRtpTransceiver.prototype.setCodecPreferences && RTCRtpSender.getCapabilities) {
            const transceivers = peerConnection.getTransceivers();
            const videoCapabilities = RTCRtpSender.getCapabilities('video');
            
            if (videoCapabilities) {
              // Prioritize high-quality codecs like VP9 and H.264
              const preferredCodecs = [];
              
              // Look for VP9 first
              const vp9Codecs = videoCapabilities.codecs.filter(codec => 
                codec.mimeType.toLowerCase() === 'video/vp9');
              preferredCodecs.push(...vp9Codecs);
              
              // Then look for H.264 with high profile
              const h264Codecs = videoCapabilities.codecs.filter(codec => 
                codec.mimeType.toLowerCase() === 'video/h264');
              preferredCodecs.push(...h264Codecs);
              
              // Add remaining codecs
              const otherCodecs = videoCapabilities.codecs.filter(codec => 
                codec.mimeType.toLowerCase() !== 'video/vp9' && 
                codec.mimeType.toLowerCase() !== 'video/h264');
              preferredCodecs.push(...otherCodecs);
              
              // Set codec preferences on the first video transceiver
              const videoTransceiver = transceivers.find(t => 
                t.sender && t.sender.track && t.sender.track.kind === 'video');
              
              if (videoTransceiver && preferredCodecs.length > 0) {
                addLog('Setting codec preferences: ' + preferredCodecs.map(c => c.mimeType).join(', '));
                videoTransceiver.setCodecPreferences(preferredCodecs);
              }
            }
          }
        } catch (e) {
          addLog('Failed to set codec preferences: ' + e.message);
        }
      } else {
        // For medium quality, use default settings
        codecPreferences = {
          offerToReceiveVideo: true,
          offerToReceiveAudio: false
        };
      }
      
      const offer = await peerConnection.createOffer(codecPreferences);
      
      addLog('Setting local description: ' + offer.type);
      await peerConnection.setLocalDescription(offer);
      
      // Send the offer to the server
      addLog('Sending offer to server');
      websocketService.send({
        type: 'webrtc_offer',
        sdp: offer.sdp,
        client_id: clientId
      });
      
    } catch (error) {
      addLog('Error setting up WebRTC: ' + error.message);
      isLoading = true;
    }
  }
  
  async function handleWebRTCAnswer(answer) {
    try {
      addLog('Received WebRTC answer from server');
      if (!peerConnection) {
        addLog('No peer connection available');
        return;
      }
      
      const rtcAnswer = new RTCSessionDescription({
        type: answer.sdpType,
        sdp: answer.sdp
      });
      
      addLog('Setting remote description');
      await peerConnection.setRemoteDescription(rtcAnswer);
      addLog('Remote description set successfully');
    } catch (error) {
      addLog('Error handling WebRTC answer: ' + error.message);
    }
  }

  function handleMessage(data) {
    if (data.type === 'webrtc_answer' && data.client_id === clientId) {
      handleWebRTCAnswer(data);
    }
    
    // Handle the quality change response
    if (data.type === 'video_quality_changed' && data.client_id === clientId) {
      addLog(`Quality change to ${data.quality}: ${data.success ? 'successful' : 'failed'}`);
    }
    
    // Handle the ping message to know a new frame is available
    if (data.type === 'video_frame_ping' && data.available) {
      // We don't need to do anything here since WebRTC will handle the stream
      // But we could update UI elements if needed
    }
  }

  function handleReadyState(ready) {
    isConnected = ready;
    addLog(ready ? 'WebSocket connected' : 'WebSocket disconnected');
    if (ready) {
      // Initialize WebRTC when WebSocket connection is ready
      initWebRTC();
    } else {
      $computingStatus = false;
      isLoading = true;
      hasStream = false;
      
      // Clean up WebRTC
      if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
      }
    }
  }
  
  function restartConnection() {
    addLog('Manually restarting WebRTC connection');
    initWebRTC();
  }
  
  onMount(() => {
    addLog('Component mounted');
    // Add message handler for WebRTC signaling
    cleanupMessageHandler = websocketService.addMessageHandler(handleMessage);
    
    // Add ready state change listener
    cleanupListener = websocketService.onReadyStateChange(handleReadyState);
    
    // Check initial connection state
    isConnected = websocketService.getSocket()?.readyState === WebSocket.OPEN;
    addLog('Initial WebSocket state: ' + (isConnected ? 'connected' : 'disconnected'));
    if (isConnected) {
      initWebRTC();
    }
    
    // Add fullscreen change event listeners
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);
  });
  
  onDestroy(() => {
    addLog('Component unmounting');
    if (cleanupListener) cleanupListener();
    if (cleanupMessageHandler) cleanupMessageHandler();
    
    // Clean up WebRTC
    if (peerConnection) {
      peerConnection.close();
      peerConnection = null;
    }
    
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
    {#if !isConnected || isLoading}
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
            value={currentQuality}
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
    {isLoading}
    {isConnected}
  />
  
  <!-- Troubleshooting Panel -->
  {#if troubleshootMode}
    <div class="mt-4 p-4 bg-gray-900 rounded-lg text-gray-200 text-sm overflow-hidden">
      <div class="flex justify-between items-center mb-2">
        <h3 class="font-semibold">WebRTC Debug Information</h3>
        <div class="flex gap-2">
          <span class="text-xs text-gray-400 font-mono">
            Quality: {currentQuality}
          </span>
          
          <!-- Add direct WebSocket test button -->
          <button 
            class="bg-green-500 hover:bg-green-600 px-2 py-1 rounded text-xs mr-2"
            on:click={() => {
              try {
                addLog('Attempting direct WebSocket connection test...');
                const wsUrl = import.meta.env.VITE_WS_URL;
                addLog(`Direct connection to: ${wsUrl}`);
                
                const testSocket = new WebSocket(wsUrl);
                
                testSocket.onopen = () => {
                  addLog('Direct WebSocket connection successful!');
                  testSocket.send(JSON.stringify({
                    type: 'ping',
                    timestamp: new Date().toISOString(),
                    test: true
                  }));
                  
                  setTimeout(() => {
                    if (testSocket.readyState === WebSocket.OPEN) {
                      testSocket.close();
                      addLog('Direct test connection closed');
                    }
                  }, 5000);
                };
                
                testSocket.onmessage = (event) => {
                  addLog(`Direct test received: ${event.data.substring(0, 50)}...`);
                };
                
                testSocket.onerror = (event) => {
                  addLog(`Direct test error: ${event}`);
                };
                
                testSocket.onclose = (event) => {
                  addLog(`Direct test closed: ${event.code} ${event.reason}`);
                };
                
                // Set timeout for connection
                setTimeout(() => {
                  if (testSocket.readyState === WebSocket.CONNECTING) {
                    addLog('Direct test connection timed out');
                    testSocket.close();
                  }
                }, 10000);
              } catch (error) {
                addLog(`Error in direct test: ${error.message}`);
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
        {#each connectionLogs as log}
          <div class="font-mono text-xs">
            <span class="text-gray-400">{log.timestamp}</span>: {log.message}
          </div>
        {/each}
      </div>
      <div class="mt-2 text-xs text-gray-400">
        Connection ID: {clientId}
      </div>
    </div>
  {/if}
</div> 