<script>
  import { onMount, onDestroy } from 'svelte';
  import { fade } from 'svelte/transition';
  import { DbService } from '../../services/db';
  import { websocketService } from '../../services/websocket';
  import { parameterStore } from '../../stores/parameterStore';
  import { PoseService } from '../../services/poses';
  import { selectedUser } from '../../stores/userStore';
  import PresetTimeline from './PresetTimeline.svelte';
  import PresetCard from './PresetCard.svelte';
  import PresetCardAdd from './PresetCardAdd.svelte';
  import VideoBuffer from '../../services/videoBuffer';
  import { webrtcService } from '../../services/webrtc';

  let presets = [];
  let selectedType = 'all';
  let selectedTags = [];
  // We'll use the store's value instead of local state
  let isLoading = true;
  let isSaving = false;
  let videoBuffer;
  let saveError = '';
  let loadError = '';
  let timelineComponent;
  let regeneratingPresetId = null;
  let currentAnimationInterval = null;
  
  // Tag search autocomplete
  let tagSearchInput = '';
  let showTagSuggestions = false;
  
  // Toggle state for collapsible sections
  let showTimelines = false;
  let showPoses = true;
  
  // Filter tag suggestions based on input
  $: filteredTagSuggestions = tagSearchInput.trim()
    ? uniqueTags.filter(tag => 
        tag.toLowerCase().includes(tagSearchInput.toLowerCase()))
    : uniqueTags;
  
  // Computed properties for unique tags and users
  $: uniqueTags = Array.from(new Set(presets.flatMap(p => p.tags || []).filter(Boolean)));
  $: uniqueUsers = Array.from(new Set(presets.flatMap(p => p.users || []).filter(Boolean)));
  
  const apiUrl = import.meta.env.VITE_API_URL;

  let initialLoadComplete = false;
  
  // Function to cleanup WebSocket listener
  let cleanupPresetListener = null;
  
  async function loadPresets() {
    try {
      presets = await DbService.getAllConfigs();
      loadError = '';
      initialLoadComplete = true;
    } catch (error) {
      console.error('Failed to load presets:', error);
      loadError = 'Failed to load presets. Please try again.';
    }
  }

  function stopCurrentAnimation() {
    if (currentAnimationInterval) {
      clearInterval(currentAnimationInterval);
      currentAnimationInterval = null;
    }
  }

  async function loadPresetConfig(preset, animationOptions = {}) {
    try {
      stopCurrentAnimation();

      if (preset.type === 'timeline') {
        if (timelineComponent) {
          timelineComponent.loadTimeline(preset.data, preset.id, preset.title); // Pass the timeline ID and title
        }
        
        if (preset.data?.placedPresets) {
          for (const placedPreset of preset.data.placedPresets) {
            await loadSinglePreset(placedPreset);
          }
        }
        
        loadError = '';
        return;
      }

      if (animationOptions.stopAnimation) {
        return;
      }

      if (animationOptions.isAnimation && preset.data) {
        currentAnimationInterval = await PoseService.handleAnimationPlayback(
          preset, 
          animationOptions.fps || 4,
          animationOptions.speedFactor || 1
        );
      } else {
        await loadSinglePreset(preset);
      }

      loadError = '';
    } catch (error) {
      console.error('Failed to load preset configuration:', error);
      loadError = 'Failed to load preset. Please try again.';
    }
  }

  async function loadSinglePreset(preset) {
    if (preset.data?.environmentParams) {
      Object.entries(preset.data.environmentParams).forEach(([key, value]) => {
        parameterStore.updateParameter(key, value);
      });

      await websocketService.send({
        type: "update_parameters",
        parameters: preset.data.environmentParams,
        timestamp: new Date().toISOString()
      });
    }

    if (preset.type === 'pose' || preset.data?.pose) {
      await PoseService.loadPoseConfig(preset);
    }

    if (preset.type === 'rewards' || preset.data?.rewards) {
      if (preset.cache_file_path) {
        await websocketService.send({
          type: "load_npz_context",
          npz_path: preset.cache_file_path,
          timestamp: new Date().toISOString()
        });
      } else if (preset.data?.rewards) {
        await websocketService.send({
          type: "request_reward",
          reward: {
            rewards: preset.data.rewards,
            weights: preset.data.weights,
            combinationType: preset.data.combinationType
          },
          timestamp: new Date().toISOString()
        });
      }
    }

    await websocketService.send({
      type: "debug_model_info"
    });
  }

  async function saveCurrentTimeline() {
    const title = prompt('Enter a name for this timeline:');
    if (!title) return;

    isSaving = true;
    saveError = '';
    
    try {
      // Use the current selected user if available, otherwise save without a user
      let users = [];
      if ($selectedUser !== 'all' && $selectedUser !== 'add_new') {
        users = [$selectedUser];
      }
      
      const config = {
        title,
        type: 'timeline',
        users, // Include the current user or empty array if none selected
        tags: [], // Initialize with empty tags array
        data: {
          duration: timelineComponent.duration,
          placedPresets: timelineComponent.placedPresets,
          envelopes: timelineComponent.envelopes // Include envelopes
        },
        thumbnail: '' // Add placeholder thumbnail for timelines
      };
      
      await DbService.addConfig(config);
      await loadPresets();
    } catch (error) {
      console.error('Failed to save timeline:', error);
      saveError = 'Failed to save timeline. Please try again.';
    } finally {
      isSaving = false;
    }
  }

  async function saveCurrentConfig() {
    const title = prompt('Enter a name for this configuration:');
    if (!title) return;

    isSaving = true;
    saveError = '';
    
    try {
      // Verify video element is available
      const videoElement = webrtcService.videoElement;
      if (!videoElement || !videoElement.videoWidth) {
        throw new Error('Video stream not available');
      }
      
      // Make sure video source is set
      videoBuffer.setVideoSource(videoElement);
      
      // Record a 3 second video for the thumbnail
      videoBuffer.startRecording(3000);
      const videoBlob = await videoBuffer.getBuffer();
      
      const base64Thumbnail = await blobToBase64(videoBlob);
      const contextData = await getContextData();
      const config = await buildConfigFromContextData(contextData, title, base64Thumbnail);
      
      await DbService.addConfig(config);
      await loadPresets();
    } catch (error) {
      console.error('Failed to save configuration:', error);
      saveError = 'Failed to save configuration. Please try again.';
    } finally {
      isSaving = false;
    }
  }

  async function regenerateThumbnail(preset) {
    if (regeneratingPresetId) return;
    
    try {
      regeneratingPresetId = preset.id;
      stopCurrentAnimation();
      
      // Verify video element is available
      const videoElement = webrtcService.videoElement;
      if (!videoElement || !videoElement.videoWidth) {
        throw new Error('Video stream not available');
      }
      
      // Make sure video source is set
      videoBuffer.setVideoSource(videoElement);
      
      // Special handling for different preset types
      if (preset.type === 'pose' && preset.data && Array.isArray(preset.data.pose)) {
        // For pose animations, play the animation while recording
        await new Promise(async (resolve) => {
          // Start the animation playback
          currentAnimationInterval = await PoseService.handleAnimationPlayback(
            preset, 
            8, // faster playback for thumbnail
            1.5 // speed up a bit
          );
          
          // Start recording after a short delay to let the animation begin
          setTimeout(async () => {
            videoBuffer.startRecording(3000);
            const videoBlob = await videoBuffer.getBuffer();
            const base64Thumbnail = await blobToBase64(videoBlob);
            
            // Update the preset with the new thumbnail
            await DbService.updateConfig(preset.id, {
              thumbnail: base64Thumbnail
            });
            
            // Stop the animation
            stopCurrentAnimation();
            resolve();
          }, 300);
        });
      } else {
        // For static poses and other types, load normally
        // Load the preset configuration
        await loadPresetConfig(preset);
        
        // Give time for WebRTC stream to update with the new configuration
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        // Record a 3 second video for the thumbnail
        videoBuffer.startRecording(3000);
        const videoBlob = await videoBuffer.getBuffer();
        const base64Thumbnail = await blobToBase64(videoBlob);

        // Update the preset with the new thumbnail
        await DbService.updateConfig(preset.id, {
          thumbnail: base64Thumbnail
        });
      }

      // Refresh presets list
      await loadPresets();
      
    } catch (error) {
      console.error('Failed to regenerate thumbnail:', error);
      saveError = 'Failed to regenerate thumbnail. Please try again.';
    } finally {
      regeneratingPresetId = null;
      stopCurrentAnimation(); // Ensure animation is stopped
    }
  }

  function blobToBase64(blob) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        if (typeof reader.result === 'string') {
          const base64String = reader.result.split(',')[1];
          resolve(base64String);
        } else {
          // Handle the case where reader.result is not a string (e.g., ArrayBuffer)
          console.error('FileReader result is not a string:', reader.result);
          resolve(''); // Resolve with empty string or handle error appropriately
        }
      };
      reader.readAsDataURL(blob);
    });
  }

  async function getContextData() {
    return new Promise((resolve, reject) => {
      let modelInfo = null;
      let contextInfo = null;
      
      const cleanup = websocketService.addMessageHandler((data) => {
        if (data.type === 'debug_model_info') {
          modelInfo = data;
        } else if (data.type === 'current_context' && data.status === 'success') {
          contextInfo = data.data;
        }
        
        if (modelInfo && contextInfo) {
          if (typeof cleanup === 'function') cleanup();
          resolve({ modelInfo, contextInfo });
        }
      });

      websocketService.send({ type: "debug_model_info" });
      websocketService.send({ type: "get_current_context" });

      setTimeout(() => {
        if (typeof cleanup === 'function') cleanup();
        reject(new Error('Timeout waiting for context data'));
      }, 5000);
    });
  }

  async function buildConfigFromContextData(contextData, title, thumbnail) {
    let rewardsData = null;
    let cacheFilePath = null;

    if (contextData.modelInfo?.active_rewards) {
      rewardsData = {
        rewards: contextData.modelInfo.active_rewards.rewards,
        weights: contextData.modelInfo.active_rewards.weights,
        combinationType: contextData.modelInfo.active_rewards.combinationType,
      };
    }

    if (contextData.contextInfo?.cache_file) {
      cacheFilePath = contextData.contextInfo.cache_file;
    }

    const environmentParams = {
      gravity: $parameterStore.gravity,
      density: $parameterStore.density,
      wind_x: $parameterStore.wind_x,
      wind_y: $parameterStore.wind_y,
      wind_z: $parameterStore.wind_z,
      viscosity: $parameterStore.viscosity,
      timestep: $parameterStore.timestep
    };

    const type = contextData.contextInfo?.active_poses ? 'pose' : 
                rewardsData ? 'rewards' : 'environment';
    
    // Use the current selected user if available
    let users = [];
    if ($selectedUser !== 'all' && $selectedUser !== 'add_new') {
      users = [$selectedUser];
    } else {
      const username = prompt('Enter your name for this preset:');
      if (username && username.trim()) {
        users = [username.trim()];
        // If we've added a new user, update the selected user in the store
        if (!uniqueUsers.includes(username.trim())) {
          // We'll wait for the next loadPresets() to update the uniqueUsers list
          // but update the selection right away
          selectedUser.set(username.trim());
        }
      }
    }
    
    return {
      title,
      type,
      thumbnail,
      cache_file_path: cacheFilePath,
      tags: [],
      users,
      data: {
        ...(rewardsData && { ...rewardsData }),
        ...(contextData.contextInfo?.active_poses && { 
          pose: contextData.contextInfo.active_poses 
        }),
        environmentParams
      }
    };
  }

  onMount(async () => {
    try {
      await loadPresets();
      
      videoBuffer = new VideoBuffer();
      await videoBuffer.initializeBuffer();
      
      // --- Add WebSocket listener for new presets ---
      // Assign the cleanup function returned by addMessageHandler
      cleanupPresetListener = websocketService.addMessageHandler((data) => {
        // Log the raw incoming data
        console.log('[WebSocket Received]', data);
        
        if (data.type === 'preset_added' && data.payload) { 
          console.log('Preset added via WebSocket:', data.payload);
          // Prepend the new preset to the list
          presets = [data.payload, ...presets];
          // Automatically load/play the newly added preset
          loadPresetConfig(data.payload);
          console.log(`[Auto Load] Triggered loading for new preset: ${data.payload.title} (ID: ${data.payload.id})`);
          // Automatically regenerate thumbnail for the new preset
          regenerateThumbnail(data.payload);
          console.log(`[Auto Thumbnail] Triggered regeneration for new preset: ${data.payload.title} (ID: ${data.payload.id})`);
        }
      });
      // ---------------------------------------------
      
      // Set video source once webrtcService's videoElement is available
      const checkVideoElement = () => {
        const videoElement = webrtcService.videoElement;
        if (videoElement) {
          videoBuffer.setVideoSource(videoElement);
          // Start continuous capture for thumbnails
          videoBuffer.startContinuousCapture();
        } else {
          // If not available yet, check again after a short delay
          setTimeout(checkVideoElement, 500);
        }
      };
      
      checkVideoElement();
    } catch (error) {
      console.error('Failed during initialization:', error);
      loadError = 'Failed to initialize. Please refresh the page.';
    } finally {
      isLoading = false;
    }
  });

  function initializeFrameUpdater() {
    // We no longer need this function for MJPEG. WebRTC will be used directly.
  }

  onDestroy(() => {
    stopCurrentAnimation();
    if (videoBuffer) {
      videoBuffer.cleanup();
    }
    // --- Clean up WebSocket listener ---
    if (typeof cleanupPresetListener === 'function') {
      cleanupPresetListener();
    }
    // --------------------------------
  });

  function filterPresets(presets) {
    return presets.filter(preset => {
      const matchesType = selectedType === 'all' || preset.type === selectedType;
      const matchesTags = selectedTags.length === 0 || 
        (preset.tags && selectedTags.some(tag => preset.tags.includes(tag)));
      const matchesUser = $selectedUser === 'all' || $selectedUser === 'add_new' ||
        (preset.users && preset.users.includes($selectedUser));
      return matchesType && matchesTags && matchesUser;
    });
  }

  async function deletePreset(id) {
    try {
      await DbService.deleteConfig(id);
      await loadPresets();
      saveError = '';
    } catch (error) {
      console.error('Failed to delete preset:', error);
      saveError = 'Failed to delete preset. Please try again.';
    }
  }
</script>

<div class="w-full bg-white rounded-lg shadow-lg p-4 mb-14">
  <div class="w-full">
    <PresetTimeline bind:this={timelineComponent} />
  </div>
  
  <div class="flex justify-between items-center mb-4">
    <div class="flex gap-4 items-center">
      <h2 class="text-lg font-bold text-gray-800">Presets</h2>
    </div>
    <div class="flex gap-4">
      <select 
        bind:value={selectedType}
        class="border rounded-md px-2 py-1 text-sm"
      >
        <option value="all">All Types</option>
        <option value="environment">Environment</option>
        <option value="rewards">Rewards</option>
        <option value="pose">Pose</option>
        <option value="timeline">Timeline</option>
      </select>

      <div class="relative min-w-[200px]">
        <!-- Selected Tags -->
        {#if selectedTags.length > 0}
          <div class="flex flex-wrap gap-1 mb-1">
            {#each selectedTags as tag}
              <span class="bg-purple-100 text-purple-800 px-2 py-0.5 rounded-full text-xs flex items-center gap-1">
                {tag}
                <button
                  class="hover:text-purple-600"
                  on:click={() => selectedTags = selectedTags.filter(t => t !== tag)}
                >
                  ×
                </button>
              </span>
            {/each}
            <button
              class="text-xs text-gray-500 hover:text-gray-700"
              on:click={() => selectedTags = []}
            >
              Clear
            </button>
          </div>
        {/if}
        
        <!-- Tag Search Input -->
        <input
          type="text"
          placeholder="Search tags..."
          class="border rounded-md px-2 py-1 text-sm w-full"
          on:focus={() => showTagSuggestions = true}
          on:input={(e) => {
            if (e.target instanceof HTMLInputElement) { 
              tagSearchInput = e.target.value;
            }
            showTagSuggestions = true;
          }}
          on:blur={() => setTimeout(() => (showTagSuggestions = false), 200)}
          bind:value={tagSearchInput}
        />
        
        <!-- Tag Suggestions Dropdown -->
        {#if showTagSuggestions && filteredTagSuggestions.length > 0}
          <div class="absolute z-50 w-full bg-white border rounded-md shadow-lg mt-1 max-h-40 overflow-y-auto">
            {#each filteredTagSuggestions.filter(tag => !selectedTags.includes(tag)) as tag}
              <button
                class="w-full text-left px-3 py-1 hover:bg-gray-100 text-sm"
                on:mousedown={() => {
                  selectedTags = [...selectedTags, tag];
                  tagSearchInput = '';
                }}
              >
                {tag}
              </button>
            {/each}
          </div>
        {/if}
      </div>

      <button 
        class="bg-purple-500 text-white px-3 py-1 text-sm font-medium rounded-md hover:bg-purple-600 transition-colors disabled:bg-gray-400"
        on:click={saveCurrentTimeline}
        disabled={isSaving}
      >
        {isSaving ? 'Saving...' : 'New Timeline'}
      </button>
      <button 
        class="bg-green-500 text-white px-3 py-1 text-sm font-medium rounded-md hover:bg-green-600 transition-colors disabled:bg-gray-400"
        on:click={saveCurrentConfig}
        disabled={isSaving}
      >
        {isSaving ? 'Saving...' : 'Save Preset'}
      </button>
    </div>
  </div>


  {#if saveError}
    <div class="text-red-500 mb-4 text-sm">{saveError}</div>
  {/if}

  {#if loadError}
    <div class="text-red-500 mb-4 text-sm">{loadError}</div>
  {/if}

  {#if isLoading}
    <p class="text-gray-500">Loading presets...</p>
  {:else}
    <!-- Toggle states are defined in the script section -->
    
    <div class="flex flex-wrap gap-4 overflow-y-auto pb-4 max-h-[calc(100vh-20rem)]">
      <!-- Display timelines first -->
      {#if filterPresets(presets).some(p => p.type === 'timeline')}
        <div class="w-full mb-2">
          <button 
            class="flex items-center w-full text-left mb-2 focus:outline-none" 
            on:click={() => showTimelines = !showTimelines}
          >
            <svg 
              xmlns="http://www.w3.org/2000/svg" 
              fill="none" 
              viewBox="0 0 24 24" 
              stroke-width="1.5" 
              stroke="currentColor" 
              class="w-4 h-4 mr-2 text-gray-700 transition-transform duration-200 {showTimelines ? 'transform rotate-90' : ''}"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            <h3 class="text-md font-medium text-gray-700">Timelines</h3>
          </button>
          
          {#if showTimelines}
            <div class="flex flex-wrap gap-4 transition-all duration-300">
              {#each filterPresets(presets).filter(p => p.type === 'timeline') as preset (preset.id)}
                <PresetCard
                  {preset}
                  onLoad={loadPresetConfig}
                  onDelete={deletePreset}
                  onRegenerateThumbnail={regenerateThumbnail}
                  isRegenerating={regeneratingPresetId === preset.id}
                  isDraggable={true}
                  allTags={uniqueTags}
                  allUsers={uniqueUsers}
                  on:tagsUpdated={() => loadPresets()}
                  on:usersUpdated={() => loadPresets()}
                  initialLoading={!initialLoadComplete}
                />
              {/each}
            </div>
          {/if}
        </div>
      {/if}
      
      <!-- Display other types (poses, rewards, environment) -->
      {#if filterPresets(presets).some(p => p.type !== 'timeline')}
        <div class="w-full">
          <button 
            class="flex items-center w-full text-left mb-2 focus:outline-none" 
            on:click={() => showPoses = !showPoses}
          >
            <svg 
              xmlns="http://www.w3.org/2000/svg" 
              fill="none" 
              viewBox="0 0 24 24" 
              stroke-width="1.5" 
              stroke="currentColor" 
              class="w-4 h-4 mr-2 text-gray-700 transition-transform duration-200 {showPoses ? 'transform rotate-90' : ''}"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            <h3 class="text-md font-medium text-gray-700">Animations, Poses & Rewards</h3>
          </button>
          
          {#if showPoses}
            <div class="flex flex-wrap gap-4 transition-all duration-300">
              {#each filterPresets(presets).filter(p => p.type !== 'timeline') as preset (preset.id)}
                <PresetCard
                  {preset}
                  onLoad={loadPresetConfig}
                  onDelete={deletePreset}
                  onRegenerateThumbnail={regenerateThumbnail}
                  isRegenerating={regeneratingPresetId === preset.id}
                  isDraggable={true}
                  allTags={uniqueTags}
                  allUsers={uniqueUsers}
                  on:tagsUpdated={() => loadPresets()}
                  on:usersUpdated={() => loadPresets()}
                  initialLoading={!initialLoadComplete}
                />
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>