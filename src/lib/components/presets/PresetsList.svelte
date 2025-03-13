<script>
  import { onMount, onDestroy } from 'svelte';
  import { fade } from 'svelte/transition';
  import { DbService } from '../../services/db';
  import { websocketService } from '../../services/websocket';
  import { parameterStore } from '../../stores/parameterStore';
  import { PoseService } from '../../services/poses';
  import PresetTimeline from './PresetTimeline.svelte';
  import PresetCard from './PresetCard.svelte';
  import VideoBuffer from '../../services/videoBuffer';

  let presets = [];
  let selectedType = 'all';
  let selectedTags = [];
  let isLoading = true;
  let isSaving = false;
  let videoBuffer;
  let saveError = '';
  let loadError = '';
  let timelineComponent;
  let regeneratingPresetId = null;
  let currentAnimationInterval = null;
  
  const apiUrl = import.meta.env.VITE_API_URL;

  async function loadPresets() {
    try {
      presets = await DbService.getAllConfigs();
      loadError = '';
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
          timelineComponent.loadTimeline(preset.data, preset.id); // Pass the timeline ID
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
      const config = {
        title,
        type: 'timeline',
        data: {
          duration: timelineComponent.duration,
          placedPresets: timelineComponent.placedPresets,
          envelopes: timelineComponent.envelopes // Include envelopes
        }
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
      videoBuffer.startRecording();
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
      
      await loadPresetConfig(preset);
      await new Promise(resolve => setTimeout(resolve, 500));
      
      videoBuffer.startRecording();
      const videoBlob = await videoBuffer.getBuffer();
      const base64Thumbnail = await blobToBase64(videoBlob);

      await DbService.updateConfig(preset.id, {
        thumbnail: base64Thumbnail
      });

      await loadPresets();
      
    } catch (error) {
      console.error('Failed to regenerate thumbnail:', error);
      saveError = 'Failed to regenerate thumbnail. Please try again.';
    } finally {
      regeneratingPresetId = null;
    }
  }

  function blobToBase64(blob) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64String = reader.result.split(',')[1];
        resolve(base64String);
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
          cleanup();
          resolve({ modelInfo, contextInfo });
        }
      });

      websocketService.send({ type: "debug_model_info" });
      websocketService.send({ type: "get_current_context" });

      setTimeout(() => {
        cleanup();
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
    
    return {
      title,
      type,
      thumbnail,
      cache_file_path: cacheFilePath,
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
      
      initializeFrameUpdater();
    } catch (error) {
      console.error('Failed during initialization:', error);
      loadError = 'Failed to initialize. Please refresh the page.';
    } finally {
      isLoading = false;
    }
  });

  function initializeFrameUpdater() {
    let retryDelay = 33;
    const maxDelay = 2000;
    const backoffFactor = 1.5;
    
    const updateFrame = async () => {
      try {
        const currentUrl = `${apiUrl}/amjpeg?${Date.now()}`;
        
        const response = await fetch(currentUrl, { method: 'HEAD' });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        videoBuffer.updateFrame(currentUrl);
        retryDelay = 33;
      } catch (error) {
        console.warn('Failed to fetch frame:', error);
        retryDelay = Math.min(retryDelay * backoffFactor, maxDelay);
      }
      
      setTimeout(updateFrame, retryDelay);
    };
    
    updateFrame();
  }

  onDestroy(() => {
    stopCurrentAnimation();
    if (videoBuffer?.stream) {
      videoBuffer.stream.getTracks().forEach(track => track.stop());
    }
  });

  function filterPresets(presets) {
    return presets.filter(preset => {
      const matchesType = selectedType === 'all' || preset.type === selectedType;
      const matchesTags = selectedTags.length === 0 || 
        (preset.tags && selectedTags.some(tag => preset.tags.includes(tag))); // Changed from every to some
      return matchesType && matchesTags;
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
    <h2 class="text-lg font-bold text-gray-800">Timeline</h2>
    <PresetTimeline bind:this={timelineComponent} />
  </div>
  
  <div class="flex justify-between items-center mb-4">
    <h2 class="text-lg font-bold text-gray-800">Presets</h2>
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

      <select
        multiple
        bind:value={selectedTags}
        class="border rounded-md px-2 py-1 text-sm min-w-[150px]"
      >
        {#each [...new Set(presets.map(p => p.tags).flat().filter(Boolean))] as tag}
          <option value={tag}>{tag}</option>
        {/each}
      </select>

      <button 
        class="bg-purple-500 text-white px-3 py-1 text-sm font-medium rounded-md hover:bg-purple-600 transition-colors disabled:bg-gray-400"
        on:click={saveCurrentTimeline}
        disabled={isSaving}
      >
        {isSaving ? 'Saving...' : 'Save Timeline'}
      </button>
      <button 
        class="bg-green-500 text-white px-3 py-1 text-sm font-medium rounded-md hover:bg-green-600 transition-colors disabled:bg-gray-400"
        on:click={saveCurrentConfig}
        disabled={isSaving}
      >
        {isSaving ? 'Saving...' : 'Save Current'}
      </button>
    </div>
  </div>

  {#if selectedTags.length > 0}
    <div class="flex gap-2 mt-2 flex-wrap">
      {#each selectedTags as tag}
        <span class="bg-purple-100 text-purple-800 px-2 py-1 rounded-full text-sm flex items-center gap-1">
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
        class="text-sm text-gray-500 hover:text-gray-700"
        on:click={() => selectedTags = []}
      >
        Clear all
      </button>
    </div>
  {/if}

  {#if saveError}
    <div class="text-red-500 mb-4 text-sm">{saveError}</div>
  {/if}

  {#if loadError}
    <div class="text-red-500 mb-4 text-sm">{loadError}</div>
  {/if}

  {#if isLoading}
    <p class="text-gray-500">Loading presets...</p>
  {:else}
    <div class="flex flex-wrap gap-4 max-h-[600px] overflow-y-auto pb-4">
      {#each filterPresets(presets) as preset (preset.id)}
        <PresetCard
          {preset}
          onLoad={loadPresetConfig}
          onDelete={deletePreset}
          onRegenerateThumbnail={regenerateThumbnail}
          isRegenerating={regeneratingPresetId === preset.id}
          isDraggable={true}
          allTags={presets.map(p => p.tags).flat().filter(Boolean)}
        />
      {/each}
    </div>
  {/if}
</div>