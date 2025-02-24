<script>
  import TagInput from "./TagsInput.svelte";
  import { DbService } from "../../services/db";
  import { fade } from 'svelte/transition';
  import { get } from 'svelte/store';
  import { currentlyPlayingPresetId } from "../../stores/playbackStore";
  import { onDestroy } from 'svelte';

  export let preset;
  export let onLoad;
  export let onDelete;
  export let onRegenerateThumbnail;
  export let isDraggable = true;
  export let isRegenerating = false;
  export let allTags = [];

  // Animation state
  let isAnimationPlaying = false;
  let animationFPS = 4;  // Frames to send per second
  let speedFactor = 1;
  let currentFrame = 0;
  let totalFrames = 0;
  let frameUpdateInterval;
  let unsubscribe;

  // Subscribe to the store to handle animation state changes
  unsubscribe = currentlyPlayingPresetId.subscribe(playingId => {
    if (playingId !== preset.id) {
      if (isAnimationPlaying) {
        stopAnimation();
      }
    } else if (!isAnimationPlaying && playingId === preset.id) {
      // Another component requested this preset to play
      handleLoad();
    }
  });

  function isAnimation(preset) {
    if (!preset.data) return false;
    
    if (Array.isArray(preset.data.pose)) {
      totalFrames = preset.data.pose.length;
      return totalFrames > 1;
    }
    
    if (Array.isArray(preset.data.qpos)) {
      totalFrames = preset.data.qpos.length;
      return totalFrames > 1;
    }
    
    return false;
  }

  function getAnimationDuration() {
    return totalFrames / speedFactor;
  }

  function startFrameUpdater() {
    if (frameUpdateInterval) {
      clearInterval(frameUpdateInterval);
    }
    
    // Adjust interval time based on speed factor
    const intervalTime = 1000 / (animationFPS * speedFactor);
    frameUpdateInterval = setInterval(() => {
      if (!isAnimationPlaying) return;
      currentFrame = (currentFrame + 1) % totalFrames;
    }, intervalTime);
  }

  async function handleLoad() {
    if (isAnimation(preset)) {
      isAnimationPlaying = true;
      currentlyPlayingPresetId.set(preset.id);
      currentFrame = 0;
      startFrameUpdater();
      onLoad(preset, { 
        isAnimation: true, 
        fps: animationFPS,
        speedFactor: speedFactor
      });
    } else {
      onLoad(preset);
    }
  }

  function stopAnimation() {
    if (isAnimationPlaying) {
      isAnimationPlaying = false;
      currentlyPlayingPresetId.set(null);
      currentFrame = 0;
      if (frameUpdateInterval) {
        clearInterval(frameUpdateInterval);
        frameUpdateInterval = null;
      }
      onLoad(preset, { stopAnimation: true });
    }
  }

  // Clean up subscription when component is destroyed
  onDestroy(() => {
    if (isAnimationPlaying) {
      stopAnimation();
    }
    if (frameUpdateInterval) {
      clearInterval(frameUpdateInterval);
    }
    if (unsubscribe) {
      unsubscribe();
    }
  });

  async function handleTagsUpdate(event) {
    const newTags = event.detail.tags;
    try {
      await DbService.updatePresetTags(preset.id, newTags);
      preset.tags = newTags;
    } catch (error) {
      console.error("Failed to update tags:", error);
    }
  }

  $: if (isAnimationPlaying && (animationFPS !== prevFPS || speedFactor !== prevSpeed)) {
    startFrameUpdater();
  }
  let prevFPS = animationFPS;
  let prevSpeed = speedFactor;
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
  {/if}

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
        <!-- Animation Controls -->
        <div class="mt-2 space-y-2">
          <div class="flex items-center">
            <label class="text-xs mr-2">FPS:</label>
            <input 
              type="range"
              bind:value={animationFPS}
              min="1"
              max="30"
              class="flex-1 h-4"
            />
            <span class="text-xs ml-2">{animationFPS}</span>
          </div>
          <div class="flex items-center">
            <label class="text-xs mr-2">Speed:</label>
            <input 
              type="range"
              bind:value={speedFactor}
              min="0.1"
              max="5"
              step="0.1"
              class="flex-1 h-4"
            />
            <span class="text-xs ml-2">{speedFactor}x</span>
          </div>
          
          <!-- Progress Bar - always visible -->
          <div class="space-y-1">
            <div class="w-full bg-gray-200 rounded-full h-2.5">
              <div 
                class="bg-blue-600 h-2.5 rounded-full transition-all" 
                style="width: {(currentFrame / Math.max(totalFrames - 1, 1)) * 100}%"
              ></div>
            </div>
            <div class="flex justify-between text-xs text-gray-600">
              <span>Frame: {currentFrame + 1}/{totalFrames}</span>
              <span>Duration: {getAnimationDuration().toFixed(2)}s</span>
            </div>
          </div>
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