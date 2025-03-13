<!-- ChatMessage.svelte -->
<script>
  import { getLastLines } from './utils.js';
  
  export let message;
  export let selectedModel;
  export let structuredResponse = null;
</script>

<div class="flex gap-2 {message.role === 'assistant' ? 'bg-gray-50' : message.role === 'system' ? 'bg-gray-100' : ''} p-4 rounded-lg">
  <div class="w-8 h-8 rounded-full flex items-center justify-center shrink-0 
              {message.role === 'assistant' 
                ? selectedModel === 'gemini' ? 'bg-purple-600' : 'bg-blue-600' 
                : message.role === 'system' ? 'bg-gray-400' : 'bg-gray-600'}">
    {#if message.role === 'assistant'}
      <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
              d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    {:else if message.role === 'system'}
      <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    {:else}
      <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    {/if}
  </div>

  <div class="flex-1 space-y-2">
    <div class="font-medium text-sm text-gray-600">
      {#if message.role === 'user'}
        You
      {:else if message.role === 'assistant'}
        {selectedModel === 'gemini' ? 'Gemini' : 'Claude'}
      {:else}
        System
      {/if}
    </div>
    
    {#if message.role === 'user'}
      <div class="text-gray-800">
        {message.content}
      </div>
    {:else if message.role === 'system'}
      <div class="text-gray-600 text-sm italic">
        {message.content}
      </div>
    {:else}
      <div class="space-y-2">
        <!-- For Gemini assistant messages -->
        {#if selectedModel === 'gemini'}
          <!-- Show preview for streaming messages -->
          {#if message.streaming}
            <div class="preview">
              {getLastLines(message.content, 3)}
            </div>
          <!-- Show only explanation text when complete -->
          {:else}
            <div class="text-gray-800">
              {#if structuredResponse && structuredResponse.explanation}
                {structuredResponse.explanation}
              {:else}
                {message.content}
              {/if}
            </div>
          {/if}
        <!-- For Claude messages -->
        {:else}
          <div class="text-gray-800">
            Generated behavior configuration:
          </div>
          <div class="bg-gray-100 rounded p-3 font-mono text-sm">
            {message.content}
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>