<!-- ChatInput.svelte -->
<script>
  export let prompt = '';
  export let isProcessing = false;
  export let selectedModel = 'claude';
  export let onSubmit;
  export let addToExisting = false;
  
  function handleKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }
</script>

<div class="border-t p-4">
  <div class="max-w-4xl mx-auto">
    <div class="mb-2 flex justify-end">
      <label class="inline-flex items-center text-sm text-gray-600">
        <input type="checkbox" bind:checked={addToExisting} class="form-checkbox h-4 w-4 text-blue-600">
        <span class="ml-2">Add to existing rewards</span>
      </label>
    </div>
    
    <form 
      on:submit|preventDefault={onSubmit}
      class="flex gap-4 items-end"
    >
      <div class="flex-1">
        <textarea
          id="prompt"
          bind:value={prompt}
          rows="3"
          on:keydown={handleKeydown}
          placeholder={selectedModel === 'gemini' 
            ? "Ask Gemini about what's happening in the video..." 
            : "Describe the desired behavior (e.g., 'Walk forward while waving both hands')"}
          class="block w-full rounded-lg border-0 py-2 px-3 text-gray-900 bg-white ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-blue-600 resize-none shadow-lg"
        ></textarea>
      </div>
      
      <button
        type="submit"
        disabled={isProcessing}
        class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed flex items-center gap-2 h-[42px] shadow-lg"
      >
        {#if isProcessing}
          <svg class="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        {:else}
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
          </svg>
        {/if}
      </button>
    </form>
  </div>
</div>