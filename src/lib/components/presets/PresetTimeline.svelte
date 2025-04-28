<script>
  import { onMount } from 'svelte';
  import { slide } from 'svelte/transition';
  import { websocketService } from '../../services/websocket';
  import { PoseService } from '../../services/poses';
  import { parameterStore } from '../../stores/parameterStore';
  import { DbService } from '../../services/db';
  import PresetTimelineEnvelope from './PresetTimelineEnvelope.svelte';
  import EnvelopeLFO from '../parameters/EnvelopeLFO.svelte';

  
  export let duration = 180;
  export let placedPresets = [];
  export let timelineId = null;
  export let timelineName = "Untitled";
  let isPlaying = false;
  let timelineRef;
  let currentTime = 0;
  let animationFrame;
  let startTime;
  let selectedPreset = null;
  let currentAnimations = new Map(); // Track running animations
  let isDraggingPreset = null;
  let envelopeComponent;
  let envelopes = {};
  
  // Zoom and pan variables
  let zoomLevel = 1;
  let viewportStart = 0;
  let viewportDuration = duration;
  let isPanning = false;
  let panStartX = 0;
  let panStartViewport = 0;
  
  // Add envelope visibility toggle
  let showEnvelope = false;

  $:console.log($parameterStore)

  // Add a watch for the showEnvelope toggle
  $: if (showEnvelope && envelopeComponent && Object.keys(envelopes).length > 0) {
    envelopeComponent.loadEnvelopes(envelopes);
  }

  // Update the button handler
  function toggleEnvelope() {
    showEnvelope = !showEnvelope;
    if (showEnvelope && envelopeComponent && Object.keys(envelopes).length > 0) {
      setTimeout(() => {
        envelopeComponent.loadEnvelopes(envelopes);
      }, 100);
    }
  }

  // Handle duration change
  function handleDurationChange(event) {
    duration = parseInt(event.target.value);
    viewportDuration = duration / zoomLevel;
    placedPresets = placedPresets.filter(preset => preset.position <= duration);
    
    // Save changes if timeline is loaded
    if (timelineId) {
      saveTimelineChanges();
    }
  }
  
  // Handle drag over
  function handleDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }

  // Variables for direct dragging
  let dragStartX = 0;
  let dragStartPosition = 0;
  let isDragging = false;
  let potentialClick = false; // Flag to differentiate click from drag

  // Handle preset dragging - direct manipulation instead of drag/drop API
  function handlePresetMouseDown(event, preset) {
    // Only handle left mouse button
    if (event.button !== 0) return;
    
    event.stopPropagation(); // Prevent timeline click
    
    isDraggingPreset = preset;
    dragStartX = event.clientX;
    dragStartPosition = preset.position;
    potentialClick = true; // Assume it might be a click initially
    isDragging = false; // Not dragging yet
    
    // Add temporary event listeners to window
    window.addEventListener('mousemove', handlePresetMouseMove);
    window.addEventListener('mouseup', handlePresetMouseUp);
  }
  
  function handlePresetMouseMove(event) {
    if (!isDraggingPreset) return; // Need a preset targeted by mousedown

    const deltaX = Math.abs(event.clientX - dragStartX);
    const moveThreshold = 5; // Pixels threshold to initiate drag

    // If movement exceeds threshold, confirm drag and cancel potential click
    if (deltaX > moveThreshold || isDragging) {
      if (!isDragging) {
        // First time drag threshold is crossed
        isDragging = true;
      }
      potentialClick = false; // It's definitely a drag, not a click

      const timelineRect = timelineRef.getBoundingClientRect();
      const currentDeltaX = event.clientX - dragStartX;
      const timeDelta = (currentDeltaX / timelineRect.width) * viewportDuration;
      
      // Calculate new position
      let newPosition = Math.max(0, dragStartPosition + timeDelta);
      
      // Make sure preset doesn't go past the timeline duration
      const maxDuration = getMaxAnimationDuration(isDraggingPreset);
      newPosition = Math.min(newPosition, duration - maxDuration);
      
      // Update the preset position in real-time
      isDraggingPreset.position = newPosition;
      
      // Force a UI update
      placedPresets = [...placedPresets];
    }
  }
  
  function handlePresetMouseUp() {
    // Clean up window listeners first
    window.removeEventListener('mousemove', handlePresetMouseMove);
    window.removeEventListener('mouseup', handlePresetMouseUp);

    if (isDragging) {
      // Drag occurred
      placedPresets = placedPresets.sort((a, b) => a.position - b.position);
      selectedPreset = isDraggingPreset; // Select the preset after dragging
      
      if (timelineId) {
        saveTimelineChanges();
      }
    } else if (potentialClick && isDraggingPreset) {
      // No drag, treat as a click
      selectedPreset = selectedPreset === isDraggingPreset ? null : isDraggingPreset;
    }
    
    // Reset state
    isDragging = false;
    potentialClick = false;
    isDraggingPreset = null;
  }

  // Calculate preset width based on duration at fixed 30fps
  function getPresetWidth(preset) {
    if (preset.data?.pose || preset.data?.qpos) {
      const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                    Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
      const fps = 30; // Fixed at 30fps as requested
      const animationDuration = frames / fps;
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
    return frames / fps;
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
    if (event.buttons === 1 && !isDraggingPreset) {
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
  
  // Handle drop for adding new presets
  function handleDrop(event) {
    event.preventDefault();
    
    try {
      // Only handle dropping new presets
      const preset = JSON.parse(event.dataTransfer.getData('preset'));
      
      const timelineRect = timelineRef.getBoundingClientRect();
      const dropX = event.clientX - timelineRect.left;
      let dropPosition = Math.min(
        Math.max(viewportStart, 
        ((dropX / timelineRect.width) * viewportDuration) + viewportStart),
        viewportStart + viewportDuration
      );
      
      let presetDuration = 2;
      if (preset.data?.pose || preset.data?.qpos) {
        const frames = Array.isArray(preset.data.pose) ? preset.data.pose.length :
                      Array.isArray(preset.data.qpos) ? preset.data.qpos.length : 1;
        // Use fixed 30fps
        const fps = 30;
        presetDuration = frames / fps;
      }

      dropPosition = Math.min(dropPosition, duration - presetDuration);

      placedPresets = [...placedPresets, {
        ...preset,
        position: dropPosition,
        duration: presetDuration
      }].sort((a, b) => a.position - b.position);
      
      // Save timeline changes after adding a new preset
      if (timelineId) {
        saveTimelineChanges();
      }
    } catch (error) {
      console.error('Failed to parse dropped preset:', error);
    }
  }

  // Handle envelope changes
  function handleEnvelopeChanged(event) {
    envelopes = event.detail.envelopes;
    saveTimelineChanges();
  }

  // Saving status indicator
  let isSaving = false;
  let saveComplete = false;
  let saveTimer;

  // Function to save timeline changes to the database
  async function saveTimelineChanges() {
    if (!timelineId) return;
    
    try {
      isSaving = true;
      saveComplete = false;
      
      // Clear any previous save complete timer
      if (saveTimer) clearTimeout(saveTimer);
      
      const timelineData = {
        duration,
        placedPresets,
        envelopes
      };
      
      await DbService.updateConfig(timelineId, {
        data: timelineData
      });
      
      console.log('Timeline updated successfully');
      
      isSaving = false;
      saveComplete = true;
      
      // Reset saved status after 3 seconds
      saveTimer = setTimeout(() => {
        saveComplete = false;
      }, 3000);
    } catch (error) {
      console.error('Failed to save timeline changes:', error);
      isSaving = false;
    }
  }

  // Handle timeline click to move playhead
  function handleTimelineClick(event) {
    if (isPanning) return;
    
    const timelineRect = timelineRef.getBoundingClientRect();
    const clickX = event.clientX - timelineRect.left;
    currentTime = (clickX / timelineRect.width) * viewportDuration + viewportStart;
    
    if (isPlaying) {
      startTime = Date.now() - (currentTime * 1000);
    }
    
    stopAllAnimations();
    
    // Apply envelope values for the current time if available
    if (showEnvelope && envelopes) {
      applyEnvelopeValues(currentTime);
    }
    
    placedPresets.forEach(preset => {
      const presetEnd = preset.position + (preset.duration || 2);
      
      if (currentTime >= preset.position && currentTime < presetEnd) {
        activatePreset(preset);
      }
    });
  }

  // Handle keydown for delete, spacebar, and arrow keys
  function handleKeydown(event) {
    // Check if event is in an input field or textarea
    const tagName = event.target.tagName.toLowerCase();
    const isInput = tagName === 'input' || tagName === 'textarea';
    
    // Only handle keyboard shortcuts if not in an input field
    if (!isInput) {
      // Handle Delete key to remove selected or dragged preset
      if (event.key === 'Delete' || event.key === 'Backspace') {
        let presetToDelete = null;

        // Prioritize deleting the currently dragged preset
        if (isDraggingPreset) {
          presetToDelete = isDraggingPreset;

          // Clean up the drag state immediately since the drag is cancelled by deletion
          window.removeEventListener('mousemove', handlePresetMouseMove);
          window.removeEventListener('mouseup', handlePresetMouseUp);
          isDragging = false;
          isDraggingPreset = null; // Clear the reference to the dragged preset

        } else if (selectedPreset) {
          // Fallback to deleting the selected preset if not dragging
          presetToDelete = selectedPreset;
        }

        if (presetToDelete) {
          // Stop any animation associated with the preset
          stopPresetAnimation(presetToDelete);
          
          // Remove the preset from the timeline using its ID for comparison
          placedPresets = placedPresets.filter(p => p.id !== presetToDelete.id);
          
          // If the deleted preset was the selected one, clear the selection
          if (selectedPreset === presetToDelete) {
            selectedPreset = null;
          }
          
          // Save timeline changes after deleting a preset
          if (timelineId) {
            saveTimelineChanges();
          }
        }
      }
      
      // Handle Spacebar for play/pause toggle
      if (event.code === 'Space') {
        event.preventDefault(); // Prevent page scroll
        togglePlayback();
      }
      
      // Handle left/right arrow keys to move 5 frames backward/forward
      // Using fps of 30 frames per second, 5 frames = 5/30 = 0.1667 seconds
      const frameJumpTime = 5 / 30; // 5 frames at 30fps
      
      if (event.code === 'ArrowLeft') {
        event.preventDefault(); // Prevent default scrolling
        jumpByTime(-frameJumpTime); // Jump backward
      }
      
      if (event.code === 'ArrowRight') {
        event.preventDefault(); // Prevent default scrolling
        jumpByTime(frameJumpTime); // Jump forward
      }
    }
  }
  
  // Function to jump by a specific time offset (positive or negative)
  function jumpByTime(timeOffset) {
    // Stop all animations when manually jumping
    stopAllAnimations();
    
    // Calculate new time, ensuring it stays within bounds
    const newTime = Math.max(0, Math.min(duration, currentTime + timeOffset));
    currentTime = newTime;
    
    // Update startTime if playing
    if (isPlaying) {
      startTime = Date.now() - (currentTime * 1000);
      playTimeline();
    }
    
    // Apply envelope values for the new time if available
    if (showEnvelope && envelopes) {
      applyEnvelopeValues(currentTime);
    }
    
    // Check if we need to activate any presets at the new time
    placedPresets.forEach(preset => {
      const presetEnd = preset.position + (preset.duration || 2);
      
      if (currentTime >= preset.position && currentTime < presetEnd) {
        activatePreset(preset);
      }
    });
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
    
    // Apply envelope values for the current time if available
    if (showEnvelope && envelopes) {
      applyEnvelopeValues(currentTime);
    }
    
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

  // Add a function to apply envelope values
  function applyEnvelopeValues(time) {
    if (!envelopes) return;
    
    // For each parameter with envelope data
    Object.keys(envelopes).forEach(param => {
      const points = envelopes[param];
      if (!points || points.length < 2) return;
      
      // Get interpolated value at current time
      const value = getValueAtTime(param, time);
      
      // Update parameter store
      parameterStore.updateParameter(param, value);
    });
  }

  // Function to get interpolated value at time
  function getValueAtTime(param, time) {
    if (!envelopes[param]) return null;
    
    const sortedPoints = [...envelopes[param]].sort((a, b) => a.time - b.time);
    
    // Handle edge cases
    if (time <= sortedPoints[0].time) return sortedPoints[0].value;
    if (time >= sortedPoints[sortedPoints.length - 1].time) return sortedPoints[sortedPoints.length - 1].value;
    
    // Find the two points that surround the current time
    for (let i = 0; i < sortedPoints.length - 1; i++) {
      const current = sortedPoints[i];
      const next = sortedPoints[i + 1];
      
      if (time >= current.time && time <= next.time) {
        // Linear interpolation between points
        const ratio = (time - current.time) / (next.time - current.time);
        return current.value + ratio * (next.value - current.value);
      }
    }
    
    return sortedPoints[0].value; // Fallback
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
        const fps = 30; // Fixed at 30fps
        
        if (Array.isArray(preset.data.pose)) {
          const elapsedSeconds = relativePosition;
          const startFrame = Math.floor(elapsedSeconds * fps);
          
          if (!currentAnimations.has(preset.id)) {
            const intervalId = await PoseService.handleAnimationPlayback(
              preset,
              fps,
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

  // Update the loadTimeline function to properly handle envelope loading
  export function loadTimeline(timelineData, id = null, name = null) {
    if (id) {
      timelineId = id;
    }
    
    if (name) {
      timelineName = name;
    } else {
      timelineName = "Untitled";
    }
    
    if (timelineData?.duration) {
      duration = timelineData.duration;
      viewportDuration = duration / zoomLevel;
    }
    if (timelineData?.placedPresets) {
      placedPresets = timelineData.placedPresets;
    }
    if (timelineData?.envelopes) {
      envelopes = timelineData.envelopes;
      // Delay loading envelopes until component is ready
      setTimeout(() => {
        if (envelopeComponent) {
          envelopeComponent.loadEnvelopes(envelopes);
        }
      }, 100);
    }
  }
  // Setup on component mount and cleanup on destroy
  onMount(() => {
    // Use document instead of window to ensure all keydown events are captured
    document.addEventListener('keydown', handleKeydown);
    
    return () => {
      document.removeEventListener('keydown', handleKeydown);
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
      }
      stopAllAnimations();
    };
  });
</script>

<div class="w-full bg-white rounded-lg shadow-lg p-4 mb-8">
  <div class="flex items-center justify-between mb-2">
    <div class="flex items-center">
      <h2 class="text-lg font-bold text-gray-800">Timeline: {timelineName}</h2>
      
      <!-- Saving indicator - always visible, changes color based on state -->
      <div class="relative ml-3 group">
        <div class="{isSaving ? 'bg-orange-500' : 'bg-blue-500'} h-3 w-3 rounded-full {isSaving ? 'animate-pulse' : ''}"></div>
        <div class="absolute z-10 hidden group-hover:block top-full left-1/2 transform -translate-x-1/2 bg-gray-800 text-white text-xs px-2 py-1 rounded whitespace-nowrap">
          {#if isSaving}
            Saving timeline...
          {:else}
            Timeline ready
          {/if}
        </div>
      </div>
    </div>
  </div>
  
  <div class="flex items-center gap-4 mb-4">
    <button 
      class="bg-gray-500 text-white px-4 py-2 rounded-md hover:bg-gray-600 relative group"
      on:click={moveToPreviousPreset}
    >
      ⏮️ Previous
    </button>


    <button 
      class="bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600 relative group"
      on:click={togglePlayback}
    >
      {isPlaying ? '⏸️ Pause' : '▶️ Play'}
      <span class="absolute hidden group-hover:inline-block text-xs -bottom-6 left-1/2 transform -translate-x-1/2 bg-gray-800 text-white px-2 py-1 rounded whitespace-nowrap">
        Press Space
      </span>
    </button>



    <button 
      class="bg-gray-500 text-white px-4 py-2 rounded-md hover:bg-gray-600 relative group"
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
    
    <!-- Add envelope toggle button -->
    <button 
      class="px-3 py-2 {showEnvelope ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-700'} rounded-md hover:opacity-90"
      on:click={toggleEnvelope}
      title="Toggle parameter envelope"
    >
      {showEnvelope ? '📈 Hide Envelope' : '📈 Show Envelope'}
    </button>
      
    <div class="text-sm text-gray-600 ml-auto">
      Current Time: {formatTime(currentTime)} / {formatTime(duration)}
    </div>
  </div>

  <div 
    bind:this={timelineRef}
    class="relative w-full h-48 bg-gray-100 rounded-md cursor-pointer"
    on:dragover={handleDragOver}
    on:drop={handleDrop}
    on:click={handleTimelineClick}
    on:wheel={handleZoom}
    on:mousedown={handlePanStart}
    on:mousemove={handlePanMove}
    on:mouseup={handlePanEnd}
    on:mouseleave={handlePanEnd}
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
          class="absolute top-10 cursor-move {selectedPreset === preset ? 'ring-2 ring-blue-500' : ''} 
                 {isDraggingPreset === preset ? 'z-10 opacity-90' : 'z-1'} transition-opacity"
          style="
            left: {((preset.position - viewportStart) / viewportDuration) * 100}%;
            width: {getPresetWidth(preset)};
          "
          on:mousedown={(e) => handlePresetMouseDown(e, preset)}
        >
          <div class="px-1 py-0.5 bg-white/80 text-xs font-medium rounded-t border border-gray-300 text-center">
            {preset.title || 'Untitled'}
          </div>
          {#if preset.thumbnail}
            <video 
              src={`data:video/webm;base64,${preset.thumbnail}`}
              class="w-full h-16 rounded-b border-2 {selectedPreset === preset ? 'border-blue-500' : 'border-gray-300'}"
              autoplay
              loop
              muted
            ></video>
          {:else}
            <div class="w-full h-16 rounded-b border-2 bg-gray-200 flex items-center justify-center 
                        {selectedPreset === preset ? 'border-blue-500' : 'border-gray-300'}">
              {preset.type || 'Preset'}
            </div>
          {/if}
        </div>
      {/if}
    {/each}
  </div>
</div>

<!-- Conditionally render the envelope component with transition -->
{#if showEnvelope}
  <div transition:slide={{ duration: 300 }}>
    <div class="flex flex-col md:flex-row gap-4">
      <!-- LFO generator component -->
      <div class="w-full md:w-1/4">
        <EnvelopeLFO 
          currentParam={envelopeComponent?.currentParam} 
          duration={duration}
          viewportStart={viewportStart}
          viewportDuration={viewportDuration}
          on:lfoGenerated={event => {
            if (envelopeComponent && event.detail.paramName) {
              // Only update the specific parameter's points, not the entire envelope object
              const paramName = event.detail.paramName;
              const newPoints = event.detail.newPoints;
              
              // Create a copy of the current envelopes
              const updatedEnvelopes = { ...envelopes };
              
              // Update only the current parameter's points
              updatedEnvelopes[paramName] = newPoints;
              
              // Update the envelope component and save
              envelopeComponent.loadEnvelopes(updatedEnvelopes);
              envelopes = updatedEnvelopes;
              saveTimelineChanges();
            }
          }}
        />
      </div>
      
      <!-- Envelope editor component -->
      <div class="w-full md:w-3/4">
        <PresetTimelineEnvelope 
          currentTime={currentTime} 
          duration={duration}
          viewportStart={viewportStart}
          viewportDuration={viewportDuration}
          timelineId={timelineId}
          on:envelopeChanged={handleEnvelopeChanged}
          bind:this={envelopeComponent}
        />
      </div>
    </div>
  </div>
{/if}

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