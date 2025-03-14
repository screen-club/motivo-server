<!-- ModelControls.svelte -->
<script>
  export let selectedModel;
  export let onSwitchModel;
  export let onClearChat;
  export let isGeminiConnected = false;
  export let autoCapture = false;
  export let onToggleAutoCapture;
  export let onCaptureFrame;
  export let onTestFlaskConnection;
</script>

<div class="flex justify-between items-center p-2 border-b">
  <!-- Model selection -->
  <div class="flex items-center space-x-2">
    <span class="text-sm text-gray-600">Model:</span>
    <div class="flex rounded-md overflow-hidden border">
      <button 
        class="px-3 py-1.5 text-sm {selectedModel === 'claude' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}" 
        on:click={() => onSwitchModel('claude')}
      >
        Claude
      </button>
      <button 
        class="px-3 py-1.5 text-sm {selectedModel === 'gemini' ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}" 
        on:click={() => onSwitchModel('gemini')}
      >
        Gemini Vision
      </button>
    </div>
  </div>
  
  <div class="flex items-center space-x-2">
    {#if selectedModel === 'gemini'}
      <button
        disabled={!isGeminiConnected}
        class="flex items-center px-2 py-1 text-sm rounded {autoCapture ? 'bg-red-500 text-white hover:bg-red-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} disabled:opacity-50 disabled:cursor-not-allowed"
        on:click={onToggleAutoCapture}
        title={autoCapture ? "Stop auto-capture" : "Start auto-capture"}
      >
        {#if autoCapture}
          <svg class="w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Stop Auto Correct
        {:else}
          <svg class="w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Auto Correct
        {/if}
      </button>
      
    
      
      <!-- Debug button for connection -->
      <button
        class="flex items-center px-2 py-1 text-sm rounded bg-green-100 text-green-700 hover:bg-green-200"
        on:click={onTestFlaskConnection}
        title="Test Flask connection"
      >
        <svg class="w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
        </svg>
        Check
      </button>
      
      <div class="flex items-center space-x-1">
        <div class={`w-2 h-2 rounded-full ${isGeminiConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
        <span class="text-xs text-gray-500">{isGeminiConnected ? 'Connected' : 'Disconnected'}</span>
      </div>
    {/if}
    
    <button
      on:click={onClearChat}
      class="text-sm px-3 py-1 text-gray-600 hover:text-gray-800 flex items-center gap-1 rounded hover:bg-gray-200"
    >
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
      Clear Chat
    </button>
  </div>
</div>