<script>
  import TagInput from "./TagsInput.svelte";
  import UserInput from "./UserInput.svelte";
  import { DbService } from "../../services/db";
  import { fade } from 'svelte/transition';
  import { get } from 'svelte/store';
  import { currentlyPlayingPresetId } from "../../stores/playbackStore";
  import { onDestroy, createEventDispatcher } from 'svelte';
  
  const dispatch = createEventDispatcher();

  export let preset;
  export let onLoad;
  export let onDelete;
  export let onRegenerateThumbnail;
  export let isDraggable = true;
  export let isRegenerating = false;
  export let allTags = [];
  export let allUsers = [];
  export let initialLoading = false;

  // Animation state
  let isAnimationPlaying = false;
  let animationFPS = 4;  // Number of poses to send in one second
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
    return (totalFrames / 30) / speedFactor; // Duration in seconds
  }

  function startFrameUpdater() {
    if (frameUpdateInterval) {
      clearInterval(frameUpdateInterval);
    }
    
    // Calculate interval based on 30 FPS base rate and speed factor
    const intervalTime = (1000 / 30) / speedFactor;
    
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

  // Function to update animation parameters while playing
  function updateAnimationParams() {
    if (isAnimationPlaying) {
      onLoad(preset, {
        isAnimation: true,
        fps: animationFPS,
        speedFactor: speedFactor,
        updateParamsOnly: true
      });
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

  let isTagsLoading = false;
  let isUsersLoading = false;
  
  async function handleTagsUpdate(event) {
    const newTags = event.detail.tags;
    isTagsLoading = true;
    try {
      await DbService.updatePresetTags(preset.id, newTags);
      preset.tags = newTags;
      // Dispatch an event to notify parent that tags have been updated
      dispatch('tagsUpdated', { tags: newTags });
    } catch (error) {
      console.error("Failed to update tags:", error);
    } finally {
      isTagsLoading = false;
    }
  }
  
  async function handleUsersUpdate(event) {
    const newUsers = event.detail.users;
    isUsersLoading = true;
    try {
      await DbService.updatePresetUsers(preset.id, newUsers);
      preset.users = newUsers;
      // Dispatch an event to notify parent that users have been updated
      dispatch('usersUpdated', { users: newUsers });
    } catch (error) {
      console.error("Failed to update users:", error);
    } finally {
      isUsersLoading = false;
    }
  }

  // Watch for FPS or speed factor changes and update animation
  $: if (isAnimationPlaying && (animationFPS !== prevFPS || speedFactor !== prevSpeed)) {
    updateAnimationParams();
    
    // Only restart the frame updater when speed changes, not when FPS changes
    if (speedFactor !== prevSpeed) {
      startFrameUpdater();
    }
    
    prevFPS = animationFPS;
    prevSpeed = speedFactor;
  }
  
  let prevFPS = animationFPS;
  let prevSpeed = speedFactor;
  
  // Handle FPS slider change
  function handleFpsChange() {
    // No need to set prevFPS here as it's handled in the reactive statement
    updateAnimationParams();
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
  <!-- We'll move the tag and user inputs to after the action buttons -->

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
        <p>Frames: {preset.data.pose?.length || preset.data.qpos?.length}</p>
        <p>Duration: {(getAnimationDuration()).toFixed(2)}s</p>
        <!-- Animation Controls -->
        <div class="mt-2 space-y-2">
          <div class="flex items-center">
            <label class="text-xs mr-2">FPS:</label>
            <input 
              type="range"
              bind:value={animationFPS}
              min="1"
              max="10"
              class="flex-1 h-4"
              on:change={handleFpsChange}
              on:input={handleFpsChange}
            />
            <span class="text-xs ml-2">{animationFPS}</span>
          </div>
          <!-- <div class="flex items-center">
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
          </div> -->
          
          <!-- Progress Bar - always visible -->
          <div class="space-y-1">
            <div class="w-full bg-gray-200 rounded-full h-2.5">
              <div 
                class="bg-blue-600 h-2.5 rounded-full transition-all" 
                style="width: {(currentFrame / Math.max(totalFrames - 1, 1)) * 100}%"
              ></div>
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
  <div class="flex justify-end gap-2 mb-3">
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
  
  <!-- Tags section with icon and divider -->
  <div class="mb-3">
    <div class="flex items-center mb-1">
      <div class="h-px flex-grow bg-indigo-100"></div>
      <div class="flex items-center px-2">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 text-indigo-500 mr-1">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6Z" />
        </svg>
        <span class="text-xs font-medium text-indigo-500">Tags</span>
      </div>
      <div class="h-px flex-grow bg-indigo-100"></div>
    </div>
    <TagInput
      tags={preset.tags || []}
      {allTags}
      on:update={handleTagsUpdate}
      placeholder="Add tags..."
      isLoading={isTagsLoading || initialLoading}
    />
  </div>
  
  <!-- Users section with icon and divider -->
  <div class="mb-3">
    <div class="flex items-center mb-1">
      <div class="h-px flex-grow bg-blue-100"></div>
      <div class="flex items-center px-2">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 text-blue-500 mr-1">
          <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
        </svg>
        <span class="text-xs font-medium text-blue-500">Users</span>
      </div>
      <div class="h-px flex-grow bg-blue-100"></div>
    </div>
    <UserInput
      users={preset.users || []}
      allUsers={allUsers}
      on:update={handleUsersUpdate}
      placeholder="Add user..."
      isLoading={isUsersLoading || initialLoading}
    />
  </div>
</div>