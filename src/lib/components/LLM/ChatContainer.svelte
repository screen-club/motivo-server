<!-- ChatContainer.svelte -->
<script>
  import ChatMessage from './ChatMessage.svelte';
  
  export let conversation = [];
  export let selectedModel;
  export let structuredResponse = null;
  export let chatContainer;
</script>

<div 
  bind:this={chatContainer}
  class="flex-1 overflow-y-auto p-4 space-y-4"
>
  {#if conversation.length === 0}
    <div class="flex items-center justify-center h-full">
      <div class="text-center text-gray-500 dark:text-gray-400 p-8">
        <h3 class="text-lg font-medium mb-2">Start a conversation</h3>
        {#if selectedModel === 'gemini'}
          <p>Use Gemini Vision to analyze the video feed in real-time.</p>
          <p class="text-sm mt-2">Try sending a snapshot or enabling auto-capture.</p>
        {:else}
          <p>Describe the behavior you'd like to create.</p>
          <p class="text-sm mt-2">For example: "Make the character walk forward while waving"</p>
        {/if}
      </div>
    </div>
  {:else}
    {#each conversation as message}
      <ChatMessage {message} {selectedModel} {structuredResponse} />
    {/each}
  {/if}
</div>