<script>
  import TagInput from "./TagsInput.svelte";
  import UserInput from "./UserInput.svelte";
  import { DbService } from "../../services/db";
  import { fade } from 'svelte/transition';
  import { get } from 'svelte/store';
  import { currentlyPlayingPresetId } from "../../stores/playbackStore";
  import { onDestroy, createEventDispatcher, onMount } from 'svelte';
  import { llmPromptStore, defaultPresetPromptStore } from '../../stores/llmInteractionStore';
  import { websocketService } from "../../services/websocket/websocketService";
  
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
  
  // Add a websocket message handler to catch 'trigger_ai' events
  let wsUnsubscribe;
  
  onMount(() => {
    // Subscribe to WebSocket messages to catch trigger_ai events
    wsUnsubscribe = websocketService.addMessageHandler((data) => {
      if (data && data.type === "trigger_ai") {
        console.log("📣 PresetCard received trigger_ai event from WebSocket");
        handleIAPrompt();
        return true; // indicate that we handled this message
      }
      return false; // we didn't handle this message
    });
  });
  
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
      // Always treat as an animation, even for single frame poses
      onLoad(preset, { 
        isAnimation: true, 
        fps: animationFPS,
        speedFactor: speedFactor
      });
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
    if (wsUnsubscribe) {
      wsUnsubscribe();
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

  function handleIAPrompt() {
    stopAnimation();
    // Use the default prompt from the store instead of hardcoding it
    const defaultPrompt = get(defaultPresetPromptStore);
    // Set the store value instead of dispatching an event
    llmPromptStore.set(defaultPrompt);
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
    <!-- Editable title field -->
    <input 
      type="text" 
      bind:value={preset.title} 
      on:blur={async () => {
        try {
          await DbService.updateConfig(preset.id, { title: preset.title });
          dispatch('titleUpdated', { title: preset.title });
        } catch (error) {
          console.error("Failed to update title:", error);
        }
      }}
      class="font-semibold text-gray-800 bg-transparent focus:bg-gray-100 focus:ring-1 focus:ring-blue-500 focus:outline-none rounded px-1 flex-1 min-w-0"
    />
    <span class="text-xs px-2 py-1 rounded-full flex-shrink-0 {preset.type === 'pose' ? 'bg-blue-100 text-blue-800' : preset.type === 'rewards' ? 'bg-green-100 text-green-800' : preset.type === 'timeline' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-800'}">
      {preset.type}
    </span>
  </div>

  <!-- Preset info -->
  <div class="text-sm text-gray-600 mb-4">
    {#if preset.data?.pose || preset.data?.qpos}
      {#if isAnimation(preset)}
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
  <div class="flex justify-between items-center gap-2 mb-3">
    {#if preset.type !== "timeline"}
      <div class="flex gap-2">
        {#if isAnimation(preset)}
          {#if isAnimationPlaying}
            <button
              class="inline-flex items-center justify-center p-2 rounded-md bg-orange-100 text-orange-700 hover:bg-orange-200 transition-colors"
              on:click={stopAnimation}
              aria-label="Stop animation"
              title="Stop"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                <path d="M5.75 3a.75.75 0 00-.75.75v12.5c0 .414.336.75.75.75h8.5a.75.75 0 00.75-.75V3.75A.75.75 0 0014.25 3h-8.5z" />
              </svg>
            </button>
          {:else}
            <button
              class="inline-flex items-center justify-center p-2 rounded-md bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors"
              on:click={handleLoad}
              aria-label="Play animation"
              title="Play"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
              </svg>
            </button>
          {/if}
        {:else}
          <button
            class="inline-flex items-center justify-center p-2 rounded-md bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors"
            on:click={() => onLoad(preset)}
            aria-label="Play preset"
            title="Play"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
              <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
            </svg>
          </button>
        {/if}
        
        <button
          class="inline-flex items-center justify-center px-2.5 py-1.5 rounded-md bg-purple-100 text-purple-700 hover:bg-purple-200 transition-colors"
          on:click={handleIAPrompt}
          title="Send preset to LLM for analysis"
          aria-label="AI analysis"
        >
          <span class="text-xs font-medium">IA</span>
        </button>
      </div>
    {/if}
    
    <button
      class="inline-flex items-center justify-center p-2 rounded-md bg-red-100 text-red-700 hover:bg-red-200 transition-colors"
      on:click={() => onDelete(preset.id)}
      aria-label="Delete preset"
      title="Delete"
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
        <path fill-rule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clip-rule="evenodd" />
      </svg>
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