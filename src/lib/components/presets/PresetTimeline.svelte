<script>
  import { onMount } from 'svelte';
  import { websocketService } from '../../services/websocketService';
  import { PoseService } from '../../services/poses';
  
  export let duration = 30;
  export let placedPresets = [];
  let isPlaying = false;
  let timelineRef;
  let currentTime = 0;
  let animationFrame;
  let startTime;
  let selectedPreset = null;
  let currentAnimations = new Map(); // Track running animations
  let isDraggingPreset = null;
  
  // Handle duration change
  function handleDurationChange(event) {
    duration = parseInt(event.target.value);
    // Validate existing preset positions against new duration
    placedPresets = placedPresets.filter(preset => preset.position <= duration);
  }
  
  // Handle drag over
  function handleDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }

  // Handle preset dragging
  function handlePresetDragStart(event, preset) {
    isDraggingPreset = preset;
    event.dataTransfer.setData('preset_move', 'true');
  }

  // Calculate preset width based on duration
  function getPresetWidth(preset) {
    if (preset.data?.pose || preset.data?.qpos) {
      // For animations, calculate width based on number of frames and FPS
      const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                    Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
      const fps = preset.data.fps || PoseService.CONFIG.DEFAULT_FPS;
      const speedFactor = preset.data.speedFactor || 1;
      const animationDuration = (frames / fps) / speedFactor;
      return `${(animationDuration / duration) * 100}%`;
    }
    // Default width for non-animation presets (2 seconds)
    return `${(2 / duration) * 100}%`;
  }
  
  // Handle drop for both new presets and moving existing ones
  function handleDrop(event) {
    event.preventDefault();
    const timelineRect = timelineRef.getBoundingClientRect();
    const dropX = event.clientX - timelineRect.left;
    let dropPosition = Math.min(Math.max(0, (dropX / timelineRect.width) * duration), duration);

    if (isDraggingPreset) {
      // Move existing preset
      placedPresets = placedPresets
        .map(p => p === isDraggingPreset ? { ...p, position: dropPosition } : p)
        .sort((a, b) => a.position - b.position);
      isDraggingPreset = null;
    } else {
      try {
        // Add new preset
        const preset = JSON.parse(event.dataTransfer.getData('preset'));
        
        // Calculate preset duration
        let presetDuration = 2; // Default 2 seconds for non-animation presets
        if (preset.data?.pose || preset.data?.qpos) {
          const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                        Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
          const fps = preset.data.fps || PoseService.CONFIG.DEFAULT_FPS;
          const speedFactor = preset.data.speedFactor || 1;
          presetDuration = (frames / fps) / speedFactor;
        }

        // Check if the drop position plus duration exceeds timeline duration
        dropPosition = Math.min(dropPosition, duration - presetDuration);

        placedPresets = [...placedPresets, {
          ...preset,
          position: dropPosition,
          duration: presetDuration
        }].sort((a, b) => a.position - b.position);
      } catch (error) {
        console.error('Failed to parse dropped preset:', error);
      }
    }
  }

  // Handle timeline click to move playhead
  function handleTimelineClick(event) {
    const timelineRect = timelineRef.getBoundingClientRect();
    const clickX = event.clientX - timelineRect.left;
    currentTime = (clickX / timelineRect.width) * duration;
    
    // Update startTime if playing
    if (isPlaying) {
      startTime = Date.now() - (currentTime * 1000);
    }
    
    // Stop all current animations
    stopAllAnimations();
    
    // Check if clicked within any preset's duration
    placedPresets.forEach(preset => {
      const presetEnd = preset.position + (preset.duration || 2);
      if (currentTime >= preset.position && currentTime < presetEnd) {
        activatePreset(preset);
      }
    });
  }

  // Handle preset selection
  function handlePresetClick(event, preset) {
    event.stopPropagation();
    selectedPreset = selectedPreset === preset ? null : preset;
  }

  // Handle keydown for delete
  function handleKeydown(event) {
    if (event.key === 'Delete' && selectedPreset) {
      stopPresetAnimation(selectedPreset);
      placedPresets = placedPresets.filter(p => p !== selectedPreset);
      selectedPreset = null;
    }
  }

  // Stop specific preset animation
  function stopPresetAnimation(preset) {
    if (currentAnimations.has(preset.id)) {
      clearInterval(currentAnimations.get(preset.id));
      currentAnimations.delete(preset.id);
      PoseService.stopCurrentAnimation();
    }
  }

  // Stop all animations
  function stopAllAnimations() {
    currentAnimations.forEach(intervalId => clearInterval(intervalId));
    currentAnimations.clear();
    PoseService.stopCurrentAnimation();
  }

  // Move to next/previous preset
  function moveToNextPreset() {
    const nextPreset = placedPresets.find(preset => preset.position > currentTime);
    if (nextPreset) {
      currentTime = nextPreset.position;
      if (isPlaying) {
        startTime = Date.now() - (currentTime * 1000);
      }
      stopAllAnimations();
      activatePreset(nextPreset);
    }
  }

  function moveToPreviousPreset() {
    const previousPreset = [...placedPresets]
      .reverse()
      .find(preset => preset.position < currentTime);
    if (previousPreset) {
      currentTime = previousPreset.position;
      if (isPlaying) {
        startTime = Date.now() - (currentTime * 1000);
      }
      stopAllAnimations();
      activatePreset(previousPreset);
    }
  }
  
  // Handle play/pause
  function togglePlayback() {
    isPlaying = !isPlaying;
    
    if (isPlaying) {
      startTime = Date.now() - (currentTime * 1000);
      playTimeline();
    } else {
      cancelAnimationFrame(animationFrame);
      stopAllAnimations();
    }
  }
  
  // Timeline playback logic
  function playTimeline() {
    const prevTime = currentTime;
    currentTime = (Date.now() - startTime) / 1000;
    
    // Check for presets that need to be activated/deactivated
    placedPresets.forEach(preset => {
      const presetEnd = preset.position + (preset.duration || 2);
      
      // If we just entered the preset's duration
      if (prevTime < preset.position && currentTime >= preset.position) {
        activatePreset(preset);
      }
      // If we just left the preset's duration
      else if (prevTime < presetEnd && currentTime >= presetEnd) {
        stopPresetAnimation(preset);
      }
    });
    
    if (currentTime >= duration) {
      currentTime = 0;
      startTime = Date.now();
      stopAllAnimations();
    }
    
    if (isPlaying) {
      animationFrame = requestAnimationFrame(playTimeline);
    }
  }
  
  // Activate preset via websocket
  async function activatePreset(preset) {
    try {
      if (preset.data?.environmentParams) {
        await websocketService.send({
          type: "update_parameters",
          parameters: preset.data.environmentParams,
          timestamp: new Date().toISOString()
        });
      }
      
      if (preset.type === 'pose' || preset.data?.pose) {
        const relativePosition = currentTime - preset.position;
        const fps = preset.data.fps || PoseService.CONFIG.DEFAULT_FPS;
        const speedFactor = preset.data.speedFactor || 1;
        
        if (Array.isArray(preset.data.pose)) {
          // Calculate starting frame based on current position in timeline
          const elapsedSeconds = relativePosition;
          const startFrame = Math.floor(elapsedSeconds * fps * speedFactor);
          
          // Only start animation if not already running for this preset
          if (!currentAnimations.has(preset.id)) {
            const intervalId = await PoseService.handleAnimationPlayback(
              preset,
              fps * speedFactor,
              startFrame
            );
            if (intervalId) {
              currentAnimations.set(preset.id, intervalId);
            }
          }
        } else {
          // Handle single pose
          await PoseService.loadPoseConfig(preset);
        }
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
    } catch (error) {
      console.error('Failed to activate preset:', error);
    }
  }

  // Function to load timeline data
  export function loadTimeline(timelineData) {
    if (timelineData?.duration) {
      duration = timelineData.duration;
    }
    if (timelineData?.placedPresets) {
      placedPresets = timelineData.placedPresets;
    }
  }
  
  // Cleanup on component destroy
  onMount(() => {
    window.addEventListener('keydown', handleKeydown);
    return () => {
      window.removeEventListener('keydown', handleKeydown);
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
      }
      stopAllAnimations();
    };
  });
</script>

<div class="w-full bg-white rounded-lg shadow-lg p-4 mb-8">
  <div class="flex items-center gap-4 mb-4">
    <!-- Previous button -->
    <button 
      class="bg-gray-500 text-white px-4 py-2 rounded-md hover:bg-gray-600"
      on:click={moveToPreviousPreset}
    >
      ⏮️ Previous
    </button>

    <!-- Play/pause button -->
    <button 
      class="bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600"
      on:click={togglePlayback}
    >
      {isPlaying ? '⏸️ Pause' : '▶️ Play'}
    </button>

    <!-- Next button -->
    <button 
      class="bg-gray-500 text-white px-4 py-2 rounded-md hover:bg-gray-600"
      on:click={moveToNextPreset}
    >
      ⏭️ Next
    </button>
    
    <div class="flex items-center gap-2">
      <input 
        type="range" 
        min="30" 
        max="180" 
        step="30" 
        bind:value={duration}
        on:input={handleDurationChange}
        class="w-48"
      />
      <span class="text-sm text-gray-600">{duration}s</span>
    </div>
  </div>

  <div 
    bind:this={timelineRef}
    class="relative w-full h-24 bg-gray-100 rounded-md cursor-pointer"
    on:dragover={handleDragOver}
    on:drop={handleDrop}
    on:click={handleTimelineClick}
  >
    <!-- Timeline markers -->
    {#each Array(duration + 1) as _, i}
      <div 
        class="absolute h-2 w-px bg-gray-300" 
        style="left: {(i / duration) * 100}%"
      ></div>
    {/each}
    
    <!-- Playhead -->
    <div 
      class="absolute top-0 w-px h-full bg-red-500"
      style="left: {(currentTime / duration) * 100}%"
    ></div>
    
    <!-- Placed presets -->
    {#each placedPresets as preset}
      <div 
        class="absolute top-4 cursor-move {selectedPreset === preset ? 'ring-2 ring-blue-500' : ''}"
        style="
          left: {(preset.position / duration) * 100}%;
          width: {getPresetWidth(preset)};
        "
        draggable="true"
        on:dragstart={(e) => handlePresetDragStart(e, preset)}
        on:click={(e) => handlePresetClick(e, preset)}
      >
        {#if preset.thumbnail}
          <video 
            src={`data:video/webm;base64,${preset.thumbnail}`}
            class="w-full h-12 rounded border-2 {selectedPreset === preset ? 'border-blue-500' : 'border-gray-300'}"
            autoplay
            loop
            muted
          ></video>
        {/if}
      </div>
    {/each}
  </div>
</div>

<style>
  input[type="range"] {
    -webkit-appearance: none;
    height: 4px;
    background: #e2e8f0;
    border-radius: 2px;
  }

  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    background: #3b82f6;
    border-radius: 50%;
    cursor: pointer;
  }
</style>