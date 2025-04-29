<script>
  import TagInput from "./TagsInput.svelte";
  import UserInput from "./UserInput.svelte";
  import { DbService } from "../../services/db";
  import { fade } from 'svelte/transition';
  import { get } from 'svelte/store';
  import { tick } from 'svelte';
  import { currentlyPlayingPresetId } from "../../stores/playbackStore";
  import { onDestroy, createEventDispatcher, onMount } from 'svelte';
  import { llmPromptStore, defaultPresetPromptStore } from '../../stores/llmInteractionStore';
  import { websocketService } from "../../services/websocket/websocketService";
  import { getApiUrl } from '../../utils/api';
  
  const dispatch = createEventDispatcher();

  // Component props using runes syntax
  let {
    preset,
    onLoad,
    onDelete,
    onRegenerateThumbnail,
    isDraggable = true,
    isRegenerating = false,
    allTags = [],
    allUsers = [],
    initialLoading = false
  } = $props();

  // RE-ADD State for async thumbnail loading
  let thumbnailData = $state(null);
  let isThumbnailLoading = $state(false);

  // State for delete feedback
  let isDeleting = false;

  // Animation state
  let isAnimationPlaying = $state(false);
  let animationFPS = $state(4);  // Number of poses to send in one second
  let speedFactor = $state(1);
  let currentFrame = $state(0);
  let totalFrames = $state(1);
  let frameUpdateInterval;
  let unsubscribe;
  
  // Add a websocket message handler to catch 'trigger_ai' events
  let wsUnsubscribe;
  
  // RE-ADD fetchThumbnail function
  async function fetchThumbnail() {
    if (!preset || !preset.id || thumbnailData) return;
    isThumbnailLoading = true;
    try {
      const apiUrl = getApiUrl();
      const response = await fetch(`${apiUrl}/api/presets/${preset.id}/thumbnail`);
      if (!response.ok) {
        // Log the 404 specifically, don't throw an error for it
        if (response.status === 404) {
          console.log(`Preset ${preset.id}: Thumbnail not found (404).`);
          thumbnailData = null; // Ensure it's null if not found
        } else {
          throw new Error(`Failed to fetch thumbnail: ${response.statusText}`);
        }
      } else {
          const data = await response.json();
          thumbnailData = data.thumbnail; // May be null if no thumbnail exists
          console.log(`Preset ${preset.id}: fetchThumbnail received data, thumbnailData is now:`, thumbnailData ? thumbnailData.substring(0, 30) + '...' : thumbnailData);
      }
    } catch (error) {
      console.error(`Error fetching thumbnail for preset ${preset.id}:`, error);
      thumbnailData = null; // Set to null on error
    } finally {
      isThumbnailLoading = false;
    }
  }
  
  
  onMount(() => {
    // RE-ADD call to fetchThumbnail if preset lacks thumbnail initially
    // This handles the initial load case where thumbnails aren't sent with the list
    if (preset && !preset.thumbnail) {
      fetchThumbnail();
    }

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
  
  // Reactive statement to refetch thumbnail if the preset prop changes *and* it lacks a thumbnail
  $effect(() => {
    const currentPresetId = preset?.id;
    const hasPresetThumbnail = !!preset?.thumbnail;
    const hasLightweightIndicator = !!preset?.has_thumbnail;

    console.log(`PresetCard effect: ID=${currentPresetId}, Prop has thumbnail=${hasPresetThumbnail}, Has thumbnail indicator=${hasLightweightIndicator}, Local thumbnailData exists=${!!thumbnailData}`);

    // Case 1: We have a lightweight preset with has_thumbnail=true but no actual thumbnail data
    if (currentPresetId && !hasPresetThumbnail && hasLightweightIndicator && !thumbnailData) {
      console.log(`Preset ${currentPresetId}: Lightweight preset indicates it has a thumbnail, fetching it.`);
      fetchThumbnail();
    } 
    // Case 2: Regular case - no thumbnail in prop and no indicator that one exists
    else if (currentPresetId && !hasPresetThumbnail && !hasLightweightIndicator && !thumbnailData) {
      console.log(`Preset ${currentPresetId}: No thumbnail indicators.`);
      // Don't fetch if there's no indication a thumbnail exists
    }
    // Case 3: We have the thumbnail data in the prop already
    else if (currentPresetId && hasPresetThumbnail) {
      // If the prop *does* have a thumbnail (e.g., after regeneration update),
      // clear any old async-loaded data to ensure the prop value is used.
      if (thumbnailData) { // Only clear if local data actually exists
        console.log(`Preset ${currentPresetId}: Prop has thumbnail, clearing local thumbnailData.`);
        thumbnailData = null; 
      }
    }
  });

  // Subscribe to the store to handle animation state changes
  unsubscribe = currentlyPlayingPresetId.subscribe(playingId => {
    // If another preset started playing, stop this one
    if (playingId !== preset.id) {
      if (isAnimationPlaying) {
        console.log(`Preset ${preset.id}: Stopping animation because preset ${playingId} is now playing`);
        isAnimationPlaying = false;
        if (frameUpdateInterval) {
          clearInterval(frameUpdateInterval);
          frameUpdateInterval = null;
        }
      }
    } 
    // If this preset is now playing according to the store but not locally, start it
    else if (!isAnimationPlaying && playingId === preset.id) {
      console.log(`Preset ${preset.id}: Starting animation because store indicates it should be playing`);
      isAnimationPlaying = true;
      // Don't call handleLoad here to avoid infinite loops - the card that triggered this update
      // already called onLoad, so we just need to update our local state
    }
  });

  // Effect to update totalFrames when the preset changes
  $effect(() => {
    if (preset.data?.pose?.length > 0) {
      totalFrames = preset.data.pose.length;
    } else if (preset.data?.qpos?.length > 0) {
      totalFrames = preset.data.qpos.length;
    } else {
      totalFrames = 1;
    }
    
    // Safety check - ensure animation isn't playing for non-animations
    if (totalFrames <= 1 && isAnimationPlaying) {
      stopAnimation();
    }
  });

  // Computed property to determine if it's an animation (avoids side effects in function)
  let isPresetAnimation = $derived(totalFrames > 1);

  function getAnimationDuration() {
    // Use the reactive totalFrames state variable
    return (totalFrames / 30) / speedFactor; 
  }

  function startFrameUpdater() {
    if (frameUpdateInterval) {
      clearInterval(frameUpdateInterval);
    }
    
    // Calculate interval based on 30 FPS base rate and speed factor
    const intervalTime = (1000 / 30) / speedFactor;
    console.log(`Preset ${preset?.id}: Starting frame updater interval with time ${intervalTime.toFixed(2)}ms`); // Log interval start
    
    frameUpdateInterval = setInterval(() => {
      if (!isAnimationPlaying) return;
      const prevFrame = currentFrame;
      currentFrame = (currentFrame + 1) % totalFrames;
      // Log inside the interval
      console.log(`Preset ${preset?.id}: Frame updated ${prevFrame} -> ${currentFrame} (Total: ${totalFrames})`); 
    }, intervalTime);
  }

  async function handleLoad() {
    // Use the computed property isPresetAnimation
    if (isPresetAnimation) { 
      console.log(`Preset ${preset?.id}: Starting animation with totalFrames = ${totalFrames}`); 
      // First set the global playing state through the store
      currentlyPlayingPresetId.set(preset.id);
      // Then update local state
      isAnimationPlaying = true;
      currentFrame = 0;
      startFrameUpdater();
      // Call the parent handler to load the animation
      onLoad(preset, { 
        isAnimation: true, 
        fps: animationFPS,
        speedFactor: speedFactor
      });
    } else {
      // For single frame poses, stop any playing animations first
      currentlyPlayingPresetId.set(null); // This will signal all animation presets to stop
      // For single frame poses, just load it without changing playing state
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
        updateParamsOnly: true,
        currentFrame: currentFrame
      });
    }
  }

  function stopAnimation() {
    if (isAnimationPlaying) {
      console.log(`Preset ${preset?.id}: Stopping animation locally`);
      // First update the store to indicate no animation is playing
      currentlyPlayingPresetId.set(null);
      // Then update local state
      isAnimationPlaying = false;
      currentFrame = 0;
      if (frameUpdateInterval) {
        clearInterval(frameUpdateInterval);
        frameUpdateInterval = null;
      }
      // Notify parent component
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

  // Effect to react to animation parameter changes in runes mode
  $effect(() => {
    // Capture current values to check against previous state if needed inside the effect,
    // though direct comparison in the condition is often enough.
    const currentFPS = animationFPS;
    const currentSpeed = speedFactor;

    // Store previous values (consider using state if complex tracking needed)
    let prevFPS = animationFPS; // Initialize or get from state
    let prevSpeed = speedFactor; // Initialize or get from state

    if (isAnimationPlaying) {
      if (currentFPS !== prevFPS || currentSpeed !== prevSpeed) {
        console.log(`Animation params changed: FPS ${prevFPS}->${currentFPS}, Speed ${prevSpeed}->${currentSpeed}`);
        updateAnimationParams();

        // Only restart the frame updater when speed changes
        if (currentSpeed !== prevSpeed) {
          startFrameUpdater();
        }
        
        // Update previous values *after* comparison and action
        // In a real component, you might store these in $state if needed elsewhere
        // For this effect, just updating tracked vars is sufficient if they aren't exported/read outside
        // For this effect, just updating tracked vars is sufficient if they aren't exported/read outside
        prevFPS = currentFPS;
        prevSpeed = currentSpeed;
      }
    }
    // Cleanup function if needed for the effect (e.g., clearing intervals on component destroy)
    // return () => { /* cleanup logic */ };
  });
  
  // Handle FPS slider change
  function handleFpsChange() {
    // No need to set prevFPS here as it's handled in the reactive statement
    updateAnimationParams();
  }

  function handleKeyDown(event) {
    if (!isPresetAnimation) return;
    
    // Only handle keyboard events if this preset is being played
    if (preset.id !== $currentlyPlayingPresetId) return;
    
    switch(event.key) {
      case "ArrowLeft":
        // Previous frame
        if (currentFrame > 0) {
          currentFrame--;
        } else {
          currentFrame = totalFrames - 1; // Loop to the end
        }
        updateFrame();
        break;
      case "ArrowRight":
        // Next frame
        if (currentFrame < totalFrames - 1) {
          currentFrame++;
        } else {
          currentFrame = 0; // Loop to the start
        }
        updateFrame();
        break;
      case " ": // Space bar
        // Toggle play/pause
        if (isAnimationPlaying) {
          stopAnimation();
        } else {
          handleLoad();
        }
        event.preventDefault(); // Prevent scrolling
        break;
    }
  }
  
  // Create tick marks for the slider based on number of frames
  let tickMarks = $derived(totalFrames <= 20 ? Array.from({ length: totalFrames }).map((_, i) => i) : []);

  function updateFrame() {
    // Reset any pending animation frames
    if (frameUpdateInterval) {
      clearInterval(frameUpdateInterval);
      frameUpdateInterval = null;
    }
    
    // Update the pose to the current frame - use direct mode for immediate feedback
    onLoad(preset, { 
      isAnimation: true,
      fps: animationFPS,
      speedFactor: speedFactor,
      currentFrame: currentFrame,
      directUpdate: true // Signal that this is a direct frame update for immediate response
    });
  }

  function handleIAPrompt() {
    stopAnimation();
    // Use the default prompt from the store instead of hardcoding it
    const defaultPrompt = get(defaultPresetPromptStore);
    // Set the store value instead of dispatching an event
    llmPromptStore.set(defaultPrompt);
  }

  // Handle delete button click
  function handleDeleteClick() {
    isDeleting = true; // Set deleting state immediately
    onDelete(preset.id); // Call parent's delete function
  }
</script>

<div
  draggable={isDraggable && preset.type !== "timeline"}
  on:dragstart={(e) => {
    if (preset.type !== "timeline") {
      e.dataTransfer.setData("preset", JSON.stringify(preset));
    }
  }}
  class="flex-shrink-0 w-52 border rounded-lg p-4 bg-white shadow-sm transition-opacity duration-300 
    ${isDeleting ? 'opacity-50 pointer-events-none' : ''}
    ${preset.type !== 'timeline' ? 'cursor-move' : 'cursor-pointer'}
    focus:outline-none focus:ring-2 focus:ring-blue-500"
  on:click={() => {
    if (preset.type === "timeline") {
      onLoad(preset);
    }
  }}
  on:keydown={handleKeyDown}
  tabindex="0"
  transition:fade
>
  <!-- We'll move the tag and user inputs to after the action buttons -->

  <!-- Thumbnail section -->
  <div class="relative">
    {#if thumbnailData || preset.thumbnail}
      <video
        src={`data:video/webm;base64,${thumbnailData || preset.thumbnail}`}
        autoplay
        muted
        loop
        playsinline
        class="w-full mb-2 rounded"
        height="120"
      ></video>
    {:else if isThumbnailLoading}
      <div class="w-full h-[120px] mb-2 rounded bg-gray-100 flex items-center justify-center">
         <svg class="animate-spin h-6 w-6 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
      </div>
    {:else if isPresetAnimation}
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
    <span class="text-xs px-2 py-1 rounded-full flex-shrink-0 {preset.type === 'pose' ? (isPresetAnimation ? 'bg-indigo-100 text-indigo-800' : 'bg-blue-100 text-blue-800') : preset.type === 'rewards' ? 'bg-green-100 text-green-800' : preset.type === 'timeline' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-800'}">
      {preset.type === 'pose' && isPresetAnimation ? 'anim' : preset.type}
    </span>
  </div>

  <!-- Preset info -->
  <div class="text-sm text-gray-600 mb-4">
    {#if preset.data?.pose || preset.data?.qpos}
      {#if isPresetAnimation}
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
          
          <!-- Progress Bar -->
          <div class="space-y-1">
            <div class="w-full bg-gray-200 rounded-full h-4 relative">
              <div 
                class="bg-blue-600 h-4 rounded-full" 
                style="width: {(currentFrame / Math.max(totalFrames - 1, 1)) * 100}%"
              ></div>
              
              <!-- Tick marks for frames (only show if frames ≤ 20) -->
              {#if tickMarks.length > 0}
                <div class="absolute top-full mt-1 w-full flex justify-between px-0.5">
                  {#each tickMarks as tick}
                    <div 
                      class="w-0.5 h-1.5 bg-gray-400 {tick === currentFrame ? 'bg-blue-600' : ''}"
                      on:click={() => {
                        currentFrame = tick;
                        updateFrame();
                      }}
                    ></div>
                  {/each}
                </div>
              {/if}
              
              <input 
                type="range"
                bind:value={currentFrame}
                min="0"
                max={totalFrames - 1}
                step="1"
                class="absolute inset-0 w-full h-full opacity-25 cursor-pointer hover:opacity-50"
                style="
                  /* Hide the thumb completely */
                  -webkit-appearance: none;
                  appearance: none;
                  /* Ensure background is transparent */
                  background: transparent;
                "
                on:input={(e) => {
                  if (isAnimationPlaying) {
                    // Stop the animation if user is manually scrubbing
                    clearInterval(frameUpdateInterval);
                  }
                  // Immediately update the frame while scrubbing
                  updateFrame();
                }}
                on:change={() => {
                  // When user stops scrubbing, update the animation state
                  if (isAnimationPlaying) {
                    startFrameUpdater(); // Restart the animation
                  }
                }}
              />
            </div>
            <div class="flex justify-between text-xs text-gray-500">
              <span>0</span>
              <span>{currentFrame}</span>
              <span>{totalFrames - 1}</span>
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
        {#if isPresetAnimation}
          {#if isAnimationPlaying}
            <button
              class="inline-flex items-center justify-center p-2 rounded-md bg-orange-100 text-orange-700 hover:bg-orange-200 transition-colors"
              on:click={stopAnimation}
              aria-label="Stop animation"
              title="Stop"
            >
              <svg class="w-5 h-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                <path fill-rule="evenodd" d="M4.5 7.5a3 3 0 013-3h9a3 3 0 013 3v9a3 3 0 01-3 3h-9a3 3 0 01-3-3v-9z" clip-rule="evenodd" />
              </svg>
            </button>
          {:else}
            <button
              class="inline-flex items-center justify-center p-2 rounded-md bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors"
              on:click={handleLoad}
              aria-label="Play animation"
              title="Play"
            >
              <svg class="w-5 h-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                <path fill-rule="evenodd" d="M4.5 5.653c0-1.426 1.529-2.33 2.779-1.643l11.54 6.348c1.295.712 1.295 2.573 0 3.285L7.28 19.991c-1.25.687-2.779-.217-2.779-1.643V5.653z" clip-rule="evenodd" />
              </svg>
            </button>
          {/if}
        {:else}
          <button
            class="inline-flex items-center justify-center p-2 rounded-md bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors"
            on:click={() => {
              // Stop any playing animations first
              currentlyPlayingPresetId.set(null);
              onLoad(preset);
            }}
            aria-label="Play preset"
            title="Play"
          >
            <svg class="w-5 h-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
              <path fill-rule="evenodd" d="M4.5 5.653c0-1.426 1.529-2.33 2.779-1.643l11.54 6.348c1.295.712 1.295 2.573 0 3.285L7.28 19.991c-1.25.687-2.779-.217-2.779-1.643V5.653z" clip-rule="evenodd" />
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
      class="inline-flex items-center justify-center p-2 rounded-md bg-red-100 text-red-700 hover:bg-red-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      on:click={handleDeleteClick} 
      aria-label="Delete preset"
      title="Delete"
      disabled={isDeleting} 
    >
      {#if isDeleting}
        <!-- Simple Spinner -->
        <svg class="animate-spin h-4 w-4 text-red-700" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      {:else}
        <!-- Original Delete Icon -->
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
          <path fill-rule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clip-rule="evenodd" />
        </svg>
      {/if}
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

<style>
  /* Hide the range input thumb in all browsers */
  input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 0;
    height: 0;
  }
  
  input[type=range]::-moz-range-thumb {
    width: 0;
    height: 0;
    border: none;
  }
  
  input[type=range]::-ms-thumb {
    width: 0;
    height: 0;
  }
</style>