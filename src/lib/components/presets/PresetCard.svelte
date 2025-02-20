<script>
  import { fade } from 'svelte/transition';
  
  export let preset;
  export let onLoad;
  export let onDelete;
  export let onRegenerateThumbnail;
  export let isDraggable = true;
  export let isRegenerating = false;
</script>

<div 
  draggable={isDraggable && preset.type !== 'timeline'}
  on:dragstart={(e) => {
    if (preset.type !== 'timeline') {
      e.dataTransfer.setData('preset', JSON.stringify(preset));
    }
  }}
  class="flex-shrink-0 w-52 border rounded-lg p-4 bg-white shadow-sm {preset.type !== 'timeline' ? 'cursor-move' : 'cursor-pointer'}"
  on:click={() => {
    if (preset.type === 'timeline') {
      onLoad(preset);
    }
  }}
  transition:fade
>
  {#if preset.thumbnail && preset.type !== 'timeline'}
    <div class="relative">
      <video 
        src={`data:video/webm;base64,${preset.thumbnail}`}
        autoplay
        muted
        loop
        playsinline
        class="w-full mb-2 rounded"
        height="120"
      ></video>
      <button 
        class="absolute top-2 right-2 bg-white rounded-full p-1.5 shadow-md hover:bg-gray-100 transition-colors"
        on:click|stopPropagation={() => onRegenerateThumbnail(preset)}
        disabled={isRegenerating}
        title="Regenerate thumbnail"
      >
        <svg 
          class={`w-4 h-4 ${isRegenerating ? 'animate-spin' : ''}`} 
          xmlns="http://www.w3.org/2000/svg" 
          fill="none" 
          viewBox="0 0 24 24" 
          stroke="currentColor"
        >
          <path 
            stroke-linecap="round" 
            stroke-linejoin="round" 
            stroke-width="2" 
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" 
          />
        </svg>
      </button>
    </div>
  {/if}
    
    <div class="flex justify-between items-start mb-2">
      <h3 class="font-semibold text-gray-800">{preset.title}</h3>
      <span class="text-xs px-2 py-1 bg-gray-100 rounded-full">
        {preset.type}
      </span>
    </div>
    
    <div class="text-sm text-gray-600 mb-4">
      {#if preset.data?.environmentParams}
        G: {preset.data.environmentParams.gravity}
        D: {preset.data.environmentParams.density}
      {/if}
      {#if preset.data?.rewards}
        <br>
        {preset.data.rewards.length} rewards
        {#if preset.cache_file_path}
          <span class="text-green-600">📁 Cached</span>
        {/if}
      {/if}
      {#if preset.data?.pose}
        <br>
        Type: {preset.data.pose.type}
        {#if preset.data.pose.type === 'smpl'}
          Model: {preset.data.pose.model}
        {/if}
        Inference: {preset.data.pose.inference_type}
      {/if}
      {#if preset.type === 'timeline'}
        Duration: {preset.data.duration}s
        <br>
        Presets: {preset.data.placedPresets.length}
      {/if}
    </div>
  
    <div class="flex justify-end gap-2">
      {#if preset.type !== 'timeline'}
        <button 
          class="text-sm text-blue-600 hover:text-blue-800"
          on:click={() => onLoad(preset)}
        >
          Load
        </button>
      {/if}
      <button 
        class="text-sm text-red-600 hover:text-red-800"
        on:click={() => onDelete(preset.id)}
      >
        Delete
      </button>
    </div>
  </div>