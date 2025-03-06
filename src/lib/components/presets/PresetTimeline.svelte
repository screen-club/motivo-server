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
  let originalWidth = 0;
  let resizingSide = null; // 'left' or 'right'
  let resizePresetStartPosition = 0;
  let presetElements = new Map(); // Map to store references to preset elements
  let originalSpeedFactor = 1;
  let originalStartFrame = 0;

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

  // Calculate preset width based on duration at fixed 30fps
  function getPresetWidth(preset) {
    if (preset.data?.pose || preset.data?.qpos) {
      const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                    Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
      const fps = 30; // Fixed at 30fps as requested
      const speedFactor = preset.data.speedFactor || 1;
      const startFrame = preset.data.startFrame || 0;
      const animationDuration = ((frames - startFrame) / fps) / speedFactor;
      const width = (animationDuration / viewportDuration) * 100;
      return `${width}%`;
    }
    return `${(2 / viewportDuration) * 100}%`;
  }

  // Get animation maximum duration in seconds
  function getMaxAnimationDuration(preset) {
    if (!preset.data?.pose && !preset.data?.qpos) return 2;
    
    const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                  Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
    const fps = 30; // Fixed at 30fps
    const startFrame = preset.data.startFrame || 0;
    return (frames - startFrame) / fps;
  }

  // Store a reference to a preset element
  function bindPresetElement(element, preset) {
    if (element) {
      presetElements.set(preset.id, element);
    }
  }

  // Get the element for a preset
  function getPresetElement(preset) {
    return presetElements.get(preset.id);
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
  function handleResizeStart(event, preset, side = 'right') {
    event.stopPropagation();
    event.preventDefault();
    isResizing = true;
    resizingPreset = preset;
    resizeStartX = event.clientX;
    resizingSide = side;
    resizePresetStartPosition = preset.position;
    originalSpeedFactor = preset.data?.speedFactor || 1;
    originalStartFrame = preset.data?.startFrame || 0;
    
    const element = getPresetElement(preset);
    if (element) {
      originalWidth = element.offsetWidth;
    }
  }

  function handleResizeMove(event) {
    if (!isResizing || !resizingPreset) return;
    
    const element = getPresetElement(resizingPreset);
    if (!element) return;
    
    const timelineRect = timelineRef.getBoundingClientRect();
    const deltaX = event.clientX - resizeStartX;
    
    // Dampen the movement sensitivity
    const sensitivityFactor = 0.5;
    const dampedDeltaX = deltaX * sensitivityFactor;
    
    if (resizingSide === 'right') {
      // Get maximum possible duration for this animation
      const maxDuration = getMaxAnimationDuration(resizingPreset);
      
      // Calculate new width based on deltaX
      let newWidth = originalWidth + dampedDeltaX;
      
      // Calculate maximum allowed width based on max duration
      const maxWidth = (maxDuration * originalSpeedFactor / viewportDuration) * timelineRect.width;
      
      // Constrain newWidth between minimum and maximum
      newWidth = Math.max(20, Math.min(newWidth, maxWidth));
      element.style.width = `${newWidth}px`;
      
      // Calculate new speed factor based on width change
      const widthRatio = newWidth / originalWidth;
      const newSpeedFactor = originalSpeedFactor / widthRatio;
      
      // Update the preset data
      if (newSpeedFactor >= 0.2 && newSpeedFactor <= 5) {
        resizingPreset.data = {
          ...resizingPreset.data,
          speedFactor: newSpeedFactor
        };
      }
    } else {
      // Left side - only allow positive deltaX (making element smaller from left)
      if (dampedDeltaX <= 0) return;
      
      const maxLeftMove = Math.min(originalWidth - 20, resizePresetStartPosition / viewportDuration * timelineRect.width);
      const leftDeltaX = Math.min(maxLeftMove, dampedDeltaX);
      
      // Calculate the new width (smaller than original)
      const newWidth = Math.max(20, originalWidth - leftDeltaX);
      element.style.width = `${newWidth}px`;
      
      // Move the element to the right
      const newLeft = ((resizePresetStartPosition - viewportStart) / viewportDuration) * 100 + (leftDeltaX / timelineRect.width) * 100;
      element.style.left = `${newLeft}%`;
      
      // Calculate the new start frame (only allow increasing the start frame)
      const frames = resizingPreset.data?.pose?.length || 
                     resizingPreset.data?.qpos?.length || 60;
      const frameRatio = leftDeltaX / originalWidth;
      const startFrameChange = Math.floor(frameRatio * frames);
      const newStartFrame = Math.max(originalStartFrame, originalStartFrame + startFrameChange);
      
      // Update position and start frame
      resizingPreset.position = resizePresetStartPosition + (leftDeltaX / timelineRect.width) * viewportDuration;
      resizingPreset.data = {
        ...resizingPreset.data,
        startFrame: Math.min(frames - 10, newStartFrame)
      };
    }
  }

  function handleResizeEnd() {
    if (resizingPreset) {
      const element = getPresetElement(resizingPreset);
      if (element) {
        // Reset the style to let the calculated width take over
        element.style.width = '';
        element.style.left = '';
      }
      
      // Force a re-render to ensure all presets show correctly
      placedPresets = [...placedPresets];
    }
    
    isResizing = false;
    resizingPreset = null;
    resizeStartX = 0;
    originalWidth = 0;
    resizingSide = null;
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
          // Use fixed 30fps
          const fps = 30;
          const speedFactor = preset.data.speedFactor || 1;
          presetDuration = (frames / fps) / speedFactor;
        }

        dropPosition = Math.min(dropPosition, duration - presetDuration);

        placedPresets = [...placedPresets, {
          ...preset,
          position: dropPosition,
          duration: presetDuration,
          data: {
            ...preset.data,
            startFrame: 0, // Initialize startFrame for new presets
            speedFactor: preset.data?.speedFactor || 1
          }
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
      // Calculate actual end position taking into account resizing
      const actualDuration = getActualPresetDuration(preset);
      const presetEnd = preset.position + actualDuration;
      
      if (currentTime >= preset.position && currentTime < presetEnd) {
        activatePreset(preset);
      }
    });
  }

  // Calculate the actual duration of a preset after resizing
  function getActualPresetDuration(preset) {
    if (preset.data?.pose || preset.data?.qpos) {
      const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                    Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
      const fps = 30; // Fixed at 30fps
      const speedFactor = preset.data.speedFactor || 1;
      const startFrame = preset.data.startFrame || 0;
      return ((frames - startFrame) / fps) / speedFactor;
    }
    return preset.duration || 2;
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
      // Calculate actual end position taking into account resizing
      const actualDuration = getActualPresetDuration(preset);
      const presetEnd = preset.position + actualDuration;
      
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
      // Check if currentTime is within the valid range of the resized animation
      const actualDuration = getActualPresetDuration(preset);
      const presetEnd = preset.position + actualDuration;
      
      if (currentTime < preset.position || currentTime >= presetEnd) {
        return; // Skip if current time is outside the resized animation bounds
      }
      
      if (preset.data?.environmentParams) {
        await websocketService.send({
          type: "update_parameters",
          parameters: preset.data.environmentParams,
          timestamp: new Date().toISOString()
        });
      }
      
      if (preset.type === 'pose' || preset.data?.pose) {
        const relativePosition = currentTime - preset.position;
        const fps = 30; // Fixed at 30fps
        const speedFactor = preset.data.speedFactor || 1;
        
        if (Array.isArray(preset.data.pose)) {
          const elapsedSeconds = relativePosition;
          const startFrame = Math.floor(elapsedSeconds * fps * speedFactor) + (preset.data.startFrame || 0);
          
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

  // Function to format time for display (MM:SS)
  function formatTime(timeInSeconds) {
    const minutes = Math.floor(timeInSeconds / 60);
    const seconds = Math.floor(timeInSeconds % 60);
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  }

  // Generate time markers every 10 seconds
  function generateTimeMarkers() {
    const markers = [];
    const step = 10; // Show marker every 10 seconds
    
    for (let i = 0; i <= viewportDuration; i += step) {
      if (viewportStart + i <= duration) {
        markers.push(viewportStart + i);
      }
    }
    
    return markers;
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
    
    <div class="text-sm text-gray-600 ml-auto">
      Current Time: {formatTime(currentTime)} / {formatTime(duration)}
    </div>
  </div>

  <div 
    bind:this={timelineRef}
    class="relative w-full h-32 bg-gray-100 rounded-md cursor-pointer"
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
    <!-- Timeline markers every 10 seconds -->
    {#each generateTimeMarkers() as time}
      <div class="absolute h-full" style="left: {((time - viewportStart) / viewportDuration) * 100}%">
        <div class="h-2 w-px bg-gray-300"></div>
        <div class="text-xs text-gray-500 mt-1">
          {formatTime(time)}
        </div>
      </div>
    {/each}
    
    <!-- Playhead -->
    <div 
      class="absolute top-0 w-px h-full bg-red-500 z-10"
      style="left: {((currentTime - viewportStart) / viewportDuration) * 100}%"
    >
      <div class="bg-red-500 text-white text-xs px-1 py-0.5 rounded absolute -left-8 -top-5">
        {formatTime(currentTime)}
      </div>
    </div>
    
    <!-- Placed presets -->
    {#each placedPresets as preset}
      {#if preset.position >= viewportStart - (preset.duration || 2) && preset.position <= viewportStart + viewportDuration}
        <div 
          class="absolute top-10 cursor-move {selectedPreset === preset ? 'ring-2 ring-blue-500' : ''}"
          style="
            left: {((preset.position - viewportStart) / viewportDuration) * 100}%;
            width: {getPresetWidth(preset)};
          "
          use:bindPresetElement={preset}
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
          
          <!-- Left resize handle -->
          <div 
            class="absolute left-0 top-0 w-4 h-full cursor-ew-resize bg-green-500 opacity-20 hover:opacity-50"
            on:mousedown={(e) => handleResizeStart(e, preset, 'left')}
          ></div>
          
          <!-- Right resize handle -->
          <div 
            class="absolute right-0 top-0 w-4 h-full cursor-ew-resize bg-blue-500 opacity-20 hover:opacity-50"
            on:mousedown={(e) => handleResizeStart(e, preset, 'right')}
          ></div>
          
          <!-- Show start frame/speed info when resizing -->
          {#if resizingPreset === preset}
            <div class="absolute -bottom-6 left-0 text-xs bg-black text-white px-1 py-0.5 rounded whitespace-nowrap">
              {resizingSide === 'left' ? `Start: ${preset.data?.startFrame || 0}` : `Speed: ${(preset.data?.speedFactor || 1).toFixed(1)}x`}
            </div>
          {/if}
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