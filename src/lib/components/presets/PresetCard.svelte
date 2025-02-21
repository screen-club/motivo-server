<script>
  import TagInput from "./TagsInput.svelte";
  import { DbService } from "../../services/db";

  export let preset;
  export let onLoad;
  export let onDelete;
  export let onRegenerateThumbnail;
  export let isDraggable = true;
  export let isRegenerating = false;
  export let allTags = [];

  // Animation state
  let isAnimationPlaying = false;
  let animationFPS = 4;

  // Helper to detect if preset is an animation
  function isAnimation(preset) {
    if (!preset.data) return false;
    
    // Direct pose data check
    if (Array.isArray(preset.data.pose)) {
      return preset.data.pose.length > 1;
    }
    
    // Direct qpos data check
    if (Array.isArray(preset.data.qpos)) {
      return preset.data.qpos.length > 1;
    }
    
    return false;
  }

  // Handle animation loading and playback
  async function handleLoad() {
    if (isAnimation(preset)) {
      isAnimationPlaying = true;
      // Pass the entire preset data for proper handling in the parent
      onLoad(preset, { 
        isAnimation: true, 
        fps: animationFPS 
      });
    } else {
      onLoad(preset);
    }
  }

  // Stop animation playback
  function stopAnimation() {
    if (isAnimationPlaying) {
      isAnimationPlaying = false;
      onLoad(preset, { stopAnimation: true });
    }
  }

  async function handleTagsUpdate(event) {
    const newTags = event.detail.tags;
    try {
      await DbService.updatePresetTags(preset.id, newTags);
      preset.tags = newTags;
    } catch (error) {
      console.error("Failed to update tags:", error);
    }
  }
</script>

<div
  draggable={isDraggable && preset.type !== "timeline"}
  on:dragstart={(e) => {
    if (preset.type !== "timeline") {
      e.dataTransfer.setData("preset", JSON.stringify(preset));
    }
  }}
  class="flex-shrink-0 w-52 border rounded-lg p-4 bg-white shadow-sm {preset.type !== 'timeline'
    ? 'cursor-move'
    : 'cursor-pointer'}"
  on:click={() => {
    if (preset.type === "timeline") {
      onLoad(preset);
    }
  }}
  transition:fade
>
  <!-- Tag input -->
  <div class="mb-4">
    <TagInput
      tags={preset.tags || []}
      {allTags}
      on:update={handleTagsUpdate}
      placeholder="Add tags..."
    />
  </div>

  <!-- Thumbnail section -->
  {#if preset.type !== "timeline"}
  <div class="relative">
    {#if preset.thumbnail}
      <video
        src={`data:video/webm;base64,${preset.thumbnail}`}
        autoplay
        muted
        loop
        playsinline
        class="w-full mb-2 rounded"
        height="120"
      ></video>
    {:else if isAnimation(preset)}
      <div class="w-full h-[120px] mb-2 rounded bg-gray-100 flex items-center justify-center">
        <i class="fas fa-film text-4xl text-gray-400"></i>
      </div>
    {/if}
    <button
      class="absolute top-2 right-2 bg-white rounded-full p-1.5 shadow-md hover:bg-gray-100 transition-colors"
      on:click|stopPropagation={() => onRegenerateThumbnail(preset)}
      disabled={isRegenerating}
      title="Regenerate thumbnail"
    >
      <svg
        class={`w-4 h-4 ${isRegenerating ? "animate-spin" : ""}`}
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
{ /if}

  <!-- Title and type -->
  <div class="flex justify-between items-start mb-2">
    <h3 class="font-semibold text-gray-800">{preset.title}</h3>
    <span class="text-xs px-2 py-1 bg-gray-100 rounded-full">
      {preset.type}
    </span>
  </div>

  <!-- Preset info -->
  <div class="text-sm text-gray-600 mb-4">
    {#if preset.data?.environmentParams}
      G: {preset.data.environmentParams.gravity}
      D: {preset.data.environmentParams.density}
    {/if}
    {#if preset.data?.rewards}
      <br />
      {preset.data.rewards.length} rewards
      {#if preset.cache_file_path}
        <span class="text-green-600">📁 Cached</span>
      {/if}
    {/if}
    {#if preset.data?.pose || preset.data?.qpos}
      <br />
      {#if isAnimation(preset)}
        Frames: {preset.data.pose?.length || preset.data.qpos?.length}
        <div class="mt-1">
          <label class="text-xs">FPS:</label>
          <input 
            type="number" 
            bind:value={animationFPS}
            min="1" 
            max="30" 
            class="w-16 ml-1 px-1 py-0.5 border rounded"
          />
        </div>
      {/if}
    {/if}
    {#if preset.type === "timeline"}
      Duration: {preset.data.duration}s
      <br />
      Presets: {preset.data.placedPresets.length}
    {/if}
  </div>

  <!-- Action buttons -->
  <div class="flex justify-end gap-2">
    {#if preset.type !== "timeline"}
      {#if isAnimation(preset)}
        {#if isAnimationPlaying}
          <button
            class="text-sm text-orange-600 hover:text-orange-800"
            on:click={stopAnimation}
          >
            Stop
          </button>
        {:else}
          <button
            class="text-sm text-blue-600 hover:text-blue-800"
            on:click={handleLoad}
          >
            Play
          </button>
        {/if}
      {:else}
        <button
          class="text-sm text-blue-600 hover:text-blue-800"
          on:click={() => onLoad(preset)}
        >
          Load
        </button>
      {/if}
    {/if}
    <button
      class="text-sm text-red-600 hover:text-red-800"
      on:click={() => onDelete(preset.id)}
    >
      Delete
    </button>
  </div>
</div>