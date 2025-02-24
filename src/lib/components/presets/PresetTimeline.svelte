<script>
  import { onMount } from 'svelte';
  import { websocketService } from '../../services/websocketService';
  import { PoseService } from '../../services/poses';
  
  export let duration = 180;
  export let placedPresets = [];
  let isPlaying = false;
  let timelineRef;
  let currentTime = 0;
  let animationFrame;
  let startTime;
  let selectedPreset = null;
  let currentAnimations = new Map(); // Track running animations
  let isDraggingPreset = null;
  
  // Zoom and pan variables
  let zoomLevel = 1;
  let viewportStart = 0;
  let viewportDuration = duration;
  let isPanning = false;
  let panStartX = 0;
  let panStartViewport = 0;

  // Resize variables
  let isResizing = false;
  let resizingPreset = null;
  let resizeStartX = 0;
  let originalSpeedFactor = 1;

  // Handle duration change
  function handleDurationChange(event) {
    duration = parseInt(event.target.value);
    viewportDuration = duration / zoomLevel;
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
      const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                    Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
      const fps = preset.data.fps || PoseService.CONFIG.DEFAULT_FPS;
      const speedFactor = preset.data.speedFactor || 1;
      const animationDuration = (frames / fps) / speedFactor;
      const width = (animationDuration / viewportDuration) * 100;
      return `${width}%`;
    }
    return `${(2 / viewportDuration) * 100}%`;
  }

  // Handle zoom functionality
  function handleZoom(event) {
    event.preventDefault();
    const timelineRect = timelineRef.getBoundingClientRect();
    const mouseX = event.clientX - timelineRect.left;
    const mouseTimePosition = (mouseX / timelineRect.width) * viewportDuration + viewportStart;
    
    const zoomFactor = event.deltaY > 0 ? 1.1 : 0.9;
    const newZoomLevel = Math.max(1, Math.min(10, zoomLevel * zoomFactor));
    
    if (newZoomLevel !== zoomLevel) {
      zoomLevel = newZoomLevel;
      
      const newViewportDuration = duration / zoomLevel;
      const mousePositionRatio = (mouseTimePosition - viewportStart) / viewportDuration;
      viewportStart = mouseTimePosition - (newViewportDuration * mousePositionRatio);
      viewportDuration = newViewportDuration;
      
      viewportStart = Math.max(0, Math.min(duration - viewportDuration, viewportStart));
    }
  }

  // Handle panning
  function handlePanStart(event) {
    if (event.buttons === 1 && !isResizing && !isDraggingPreset) {
      isPanning = true;
      panStartX = event.clientX;
      panStartViewport = viewportStart;
    }
  }

  function handlePanMove(event) {
    if (!isPanning) return;
    
    const timelineRect = timelineRef.getBoundingClientRect();
    const deltaX = event.clientX - panStartX;
    const deltaTime = (deltaX / timelineRect.width) * viewportDuration;
    
    viewportStart = Math.max(0, Math.min(duration - viewportDuration, panStartViewport - deltaTime));
  }

  function handlePanEnd() {
    isPanning = false;
  }

  // Handle resize functionality
  function handleResizeStart(event, preset) {
    event.stopPropagation();
    event.preventDefault();
    isResizing = true;
    resizingPreset = preset;
    resizeStartX = event.clientX;
    originalSpeedFactor = preset.data?.speedFactor || 1;
  }

  function handleResizeMove(event) {
    if (!isResizing || !resizingPreset) return;
    
    const timelineRect = timelineRef.getBoundingClientRect();
    const deltaX = event.clientX - resizeStartX;
    const deltaRatio = deltaX / timelineRect.width;
    
    // Update speed factor with a minimum of 0.1 and maximum of 5
    const newSpeedFactor = Math.max(0.1, Math.min(5, originalSpeedFactor * (1 + deltaRatio)));
    
    // Update the preset with new speed factor
    placedPresets = placedPresets.map(p => {
      if (p === resizingPreset) {
        return {
          ...p,
          data: {
            ...p.data,
            speedFactor: newSpeedFactor,
          }
        };
      }
      return p;
    });
  }

  function handleResizeEnd() {
    isResizing = false;
    resizingPreset = null;
    resizeStartX = 0;
    originalSpeedFactor = 1;
  }
  
  // Handle drop for both new presets and moving existing ones
  function handleDrop(event) {
    event.preventDefault();
    const timelineRect = timelineRef.getBoundingClientRect();
    const dropX = event.clientX - timelineRect.left;
    let dropPosition = Math.min(
      Math.max(viewportStart, 
      ((dropX / timelineRect.width) * viewportDuration) + viewportStart),
      viewportStart + viewportDuration
    );

    if (isDraggingPreset) {
      placedPresets = placedPresets
        .map(p => p === isDraggingPreset ? { ...p, position: dropPosition } : p)
        .sort((a, b) => a.position - b.position);
      isDraggingPreset = null;
    } else {
      try {
        const preset = JSON.parse(event.dataTransfer.getData('preset'));
        
        let presetDuration = 2;
        if (preset.data?.pose || preset.data?.qpos) {
          const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                        Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
          const fps = preset.data.fps || PoseService.CONFIG.DEFAULT_FPS;
          const speedFactor = preset.data.speedFactor || 1;
          presetDuration = (frames / fps) / speedFactor;
        }

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
    if (isResizing || isPanning) return;
    
    const timelineRect = timelineRef.getBoundingClientRect();
    const clickX = event.clientX - timelineRect.left;
    currentTime = (clickX / timelineRect.width) * viewportDuration + viewportStart;
    
    if (isPlaying) {
      startTime = Date.now() - (currentTime * 1000);
    }
    
    stopAllAnimations();
    
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

  // Animation control functions
  function stopPresetAnimation(preset) {
    if (currentAnimations.has(preset.id)) {
      clearInterval(currentAnimations.get(preset.id));
      currentAnimations.delete(preset.id);
      PoseService.stopCurrentAnimation();
    }
  }

  function stopAllAnimations() {
    currentAnimations.forEach(intervalId => clearInterval(intervalId));
    currentAnimations.clear();
    PoseService.stopCurrentAnimation();
  }

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
    
    placedPresets.forEach(preset => {
      const presetEnd = preset.position + (preset.duration || 2);
      
      if (prevTime < preset.position && currentTime >= preset.position) {
        activatePreset(preset);
      }
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
          const elapsedSeconds = relativePosition;
          const startFrame = Math.floor(elapsedSeconds * fps * speedFactor);
          
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
      viewportDuration = duration / zoomLevel;
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
    <button 
      class="bg-gray-500 text-white px-4 py-2 rounded-md hover:bg-gray-600"
      on:click={moveToPreviousPreset}
    >
      ⏮️ Previous
    </button>

    <button 
      class="bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600"
      on:click={togglePlayback}
    >
      {isPlaying ? '⏸️ Pause' : '▶️ Play'}
    </button>

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
  on:wheel={handleZoom}
  on:mousedown={handlePanStart}
  on:mousemove={handlePanMove}
  on:mouseup={handlePanEnd}
  on:mouseleave={handlePanEnd}
  on:mousemove={handleResizeMove}
  on:mouseup={handleResizeEnd}
  on:mouseleave={handleResizeEnd}
>
  <!-- Timeline markers -->
  {#each Array(Math.ceil(viewportDuration) + 1) as _, i}
    <div 
      class="absolute h-2 w-px bg-gray-300" 
      style="left: {(i / viewportDuration) * 100}%"
    ></div>
  {/each}
  
  <!-- Playhead -->
  <div 
    class="absolute top-0 w-px h-full bg-red-500"
    style="left: {((currentTime - viewportStart) / viewportDuration) * 100}%"
  ></div>
  
  <!-- Placed presets -->
  {#each placedPresets as preset}
    {#if preset.position >= viewportStart && preset.position <= viewportStart + viewportDuration}
      <div 
        class="absolute top-4 cursor-move {selectedPreset === preset ? 'ring-2 ring-blue-500' : ''}"
        style="
          left: {((preset.position - viewportStart) / viewportDuration) * 100}%;
          width: {getPresetWidth(preset)};
        "
        draggable={!isResizing}
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
        
        <!-- Resize handle -->
        <div 
          class="absolute right-0 top-0 w-4 h-full cursor-ew-resize hover:bg-blue-500 hover:opacity-50"
          on:mousedown={(e) => handleResizeStart(e, preset)}
        ></div>
      </div>
    {/if}
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