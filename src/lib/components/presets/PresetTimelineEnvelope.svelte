<script>
  import { onMount, createEventDispatcher } from 'svelte';
  import { parameterStore } from '../../stores/parameterStore';
  
  // Props
  export let currentParam = "gravity";
  export let currentTime = 0;
  // Add these new props to sync with parent timeline component
  export let duration = 180;
  export let viewportStart = 0;
  export let viewportDuration = 180;
  
  // Internal state
  let envelopePoints = [];
  let canvasRef;
  let canvasWidth = 0;
  let canvasHeight = 0;
  let isDragging = false;
  let selectedPointIndex = -1;
  let hoveredPointIndex = -1; 
  let minValue = -100;
  let maxValue = 100;
  const dispatch = createEventDispatcher();
  
  // Parameter bounds remain the same
  const parameterBounds = {
    gravity: { min: -100, max: 0 },
    density: { min: 0, max: 5 },
    wind_x: { min: -20, max: 20 },
    wind_y: { min: -20, max: 20 },
    wind_z: { min: -20, max: 20 },
    viscosity: { min: 0, max: 10 },
    integrator: { min: 0, max: 2 },
    timestep: { min: 0.0001, max: 0.01 }
  };
  
  // Initialize with current parameter value
  $: {
    if (envelopePoints.length === 0 && $parameterStore && currentParam) {
      initializePoints();
    }
    
    if (currentParam && parameterBounds[currentParam]) {
      minValue = parameterBounds[currentParam].min;
      maxValue = parameterBounds[currentParam].max;
    }
  }
  
  // Update parameter based on envelope
  $: {
    if (currentTime >= 0 && envelopePoints.length >= 2) {
      const value = getValueAtTime(currentTime);
      updateParameter(value);
    }
  }
  
  function initializePoints() {
    // Initialize with at least two points
    const initialValue = $parameterStore[currentParam] || 0;
    envelopePoints = [
      { time: 0, value: initialValue },
      { time: duration, value: initialValue } // Use duration instead of hardcoded 180
    ];
    redrawCanvas();
  }
  
  function updateParameter(value) {
    parameterStore.updateParameter(currentParam, value);
  }
  
  function getValueAtTime(time) {
    // Find the surrounding points
    const sortedPoints = [...envelopePoints].sort((a, b) => a.time - b.time);
    
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

  function handleMouseDown(event) {
    // Only handle left clicks for dragging
    if (event.button !== 0) return;
    
    const rect = canvasRef.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    // Check if clicked near any existing point
    const pointRadius = 8;
    for (let i = 0; i < envelopePoints.length; i++) {
      const point = envelopePoints[i];
      // Convert time to x position based on viewport
      const pointX = ((point.time - viewportStart) / viewportDuration) * canvasWidth;
      const pointY = canvasHeight - ((point.value - minValue) / (maxValue - minValue)) * canvasHeight;
      
      const distance = Math.sqrt(Math.pow(pointX - x, 2) + Math.pow(pointY - y, 2));
      
      if (distance <= pointRadius) {
        selectedPointIndex = i;
        isDragging = true;
        return;
      }
    }
    
    // If not near any point, add a new one
    // Convert x position to time based on viewport
    const time = viewportStart + (x / canvasWidth) * viewportDuration;
    const value = minValue + ((canvasHeight - y) / canvasHeight) * (maxValue - minValue);
    
    // Make sure it's between the first and last point
    if (time > 0 && time < duration) {
      envelopePoints = [...envelopePoints, { time, value }];
      envelopePoints.sort((a, b) => a.time - b.time);
      redrawCanvas();
      
      // Update value at current time after adding a point
      updateParameter(getValueAtTime(currentTime));
    }
  }
  
  function handleContextMenu(event) {
    // Prevent the default context menu
    event.preventDefault();
    
    const rect = canvasRef.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    // Check if right-clicked on a point
    const pointRadius = 8;
    for (let i = 0; i < envelopePoints.length; i++) {
      // Don't allow deleting first or last point
      if (i === 0 || i === envelopePoints.length - 1) continue;
      
      const point = envelopePoints[i];
      // Convert time to x position based on viewport
      const pointX = ((point.time - viewportStart) / viewportDuration) * canvasWidth;
      const pointY = canvasHeight - ((point.value - minValue) / (maxValue - minValue)) * canvasHeight;
      
      const distance = Math.sqrt(Math.pow(pointX - x, 2) + Math.pow(pointY - y, 2));
      
      if (distance <= pointRadius) {
        // Remove the point
        envelopePoints = envelopePoints.filter((_, index) => index !== i);
        hoveredPointIndex = -1;
        redrawCanvas();
        updateParameter(getValueAtTime(currentTime));
        return;
      }
    }
  }
  
  function handleMouseMove(event) {
    const rect = canvasRef.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    // Handle dragging points
    if (isDragging && selectedPointIndex !== -1) {
      const point = { ...envelopePoints[selectedPointIndex] };
      
      // First and last points can only move vertically
      if (selectedPointIndex > 0 && selectedPointIndex < envelopePoints.length - 1) {
        // Convert x position to time based on viewport
        point.time = Math.max(0, Math.min(duration, 
          viewportStart + (x / canvasWidth) * viewportDuration
        ));
      }
      
      // All points can move vertically
      point.value = Math.max(minValue, Math.min(maxValue, 
        minValue + ((canvasHeight - y) / canvasHeight) * (maxValue - minValue)
      ));
      
      envelopePoints[selectedPointIndex] = point;
      redrawCanvas();
      
      // To reduce WebSocket traffic, we'll only update during dragging every 100ms
      if (!point.lastUpdate || Date.now() - point.lastUpdate > 100) {
        updateParameter(getValueAtTime(currentTime));
        point.lastUpdate = Date.now();
      }
      return;
    }
    
    // Check if hovering over a point
    let foundHoveredPoint = false;
    const pointRadius = 8;
    
    for (let i = 0; i < envelopePoints.length; i++) {
      const point = envelopePoints[i];
      // Convert time to x position based on viewport
      const pointX = ((point.time - viewportStart) / viewportDuration) * canvasWidth;
      const pointY = canvasHeight - ((point.value - minValue) / (maxValue - minValue)) * canvasHeight;
      
      const distance = Math.sqrt(Math.pow(pointX - x, 2) + Math.pow(pointY - y, 2));
      
      if (distance <= pointRadius) {
        hoveredPointIndex = i;
        foundHoveredPoint = true;
        redrawCanvas();
        break;
      }
    }
    
    // If moved away from all points
    if (!foundHoveredPoint && hoveredPointIndex !== -1) {
      hoveredPointIndex = -1;
      redrawCanvas();
    }
  }
  
  function handleMouseUp() {
    if (isDragging) {
      // Update parameter when done dragging
      updateParameter(getValueAtTime(currentTime));
    }
    
    isDragging = false;
    selectedPointIndex = -1;
  }
  
  function redrawCanvas() {
    if (!canvasRef) return;
    
    const ctx = canvasRef.getContext('2d');
    ctx.clearRect(0, 0, canvasWidth, canvasHeight);
    
    // Draw grid
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 0.5;
    
    // Vertical grid lines - adjust based on viewport
    const gridStep = calculateGridStep(viewportDuration);
    const startTime = Math.ceil(viewportStart / gridStep) * gridStep;
    
    for (let i = startTime; i <= viewportStart + viewportDuration; i += gridStep) {
      const x = ((i - viewportStart) / viewportDuration) * canvasWidth;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvasHeight);
      ctx.stroke();
      
      // Add time labels
      ctx.fillStyle = '#718096';
      ctx.font = '10px sans-serif';
      ctx.fillText(formatTime(i), x + 2, canvasHeight - 2);
    }
    
    // Horizontal grid lines
    const steps = 5;
    for (let i = 0; i <= steps; i++) {
      const y = (i / steps) * canvasHeight;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvasWidth, y);
      ctx.stroke();
      
      // Label the values
      const value = maxValue - ((i / steps) * (maxValue - minValue));
      ctx.fillStyle = '#718096';
      ctx.font = '10px sans-serif';
      ctx.fillText(value.toFixed(1), 5, y - 2);
    }
    
    // Sort points by time
    const sortedPoints = [...envelopePoints].sort((a, b) => a.time - b.time);
    
    // Draw envelope line - but only for points visible in viewport
    ctx.beginPath();
    ctx.strokeStyle = '#4299e1';
    ctx.lineWidth = 2;
    
    let started = false;
    
    sortedPoints.forEach((point, index) => {
      // Skip points outside viewport, but connect line to points just outside
      if (point.time < viewportStart - 0.1 && (index === sortedPoints.length - 1 || sortedPoints[index + 1].time > viewportStart)) {
        // This is the last point before viewport - calculate where line enters viewport
        const nextPoint = sortedPoints[index + 1];
        const ratio = (viewportStart - point.time) / (nextPoint.time - point.time);
        const value = point.value + ratio * (nextPoint.value - point.value);
        
        ctx.moveTo(0, canvasHeight - ((value - minValue) / (maxValue - minValue)) * canvasHeight);
        started = true;
      }
      else if (point.time > viewportStart + viewportDuration + 0.1 && started) {
        // This is the first point after viewport - calculate where line exits viewport
        const prevPoint = sortedPoints[index - 1];
        const ratio = (viewportStart + viewportDuration - prevPoint.time) / (point.time - prevPoint.time);
        const value = prevPoint.value + ratio * (point.value - prevPoint.value);
        
        ctx.lineTo(canvasWidth, canvasHeight - ((value - minValue) / (maxValue - minValue)) * canvasHeight);
        started = false;
      }
      else if (point.time >= viewportStart - 0.1 && point.time <= viewportStart + viewportDuration + 0.1) {
        // This point is visible in viewport
        const x = ((point.time - viewportStart) / viewportDuration) * canvasWidth;
        const y = canvasHeight - ((point.value - minValue) / (maxValue - minValue)) * canvasHeight;
        
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
    });
    
    ctx.stroke();
    
    // Draw playhead
    const playheadX = ((currentTime - viewportStart) / viewportDuration) * canvasWidth;
    
    // Only draw playhead if it's in viewport
    if (playheadX >= 0 && playheadX <= canvasWidth) {
      ctx.beginPath();
      ctx.strokeStyle = '#e53e3e';
      ctx.lineWidth = 1;
      ctx.moveTo(playheadX, 0);
      ctx.lineTo(playheadX, canvasHeight);
      ctx.stroke();
      
      // Current value indicator
      const currentValue = getValueAtTime(currentTime);
      const currentY = canvasHeight - ((currentValue - minValue) / (maxValue - minValue)) * canvasHeight;
      
      ctx.beginPath();
      ctx.fillStyle = '#e53e3e';
      ctx.arc(playheadX, currentY, 5, 0, Math.PI * 2);
      ctx.fill();
      
      // Display current value
      ctx.fillStyle = '#000';
      ctx.font = '12px sans-serif';
      ctx.fillText(
        `${currentParam}: ${currentValue.toFixed(2)}`, 
        playheadX + 10, 
        currentY - 10
      );
    }
    
    // Draw points
    sortedPoints.forEach((point, index) => {
      // Skip points outside viewport
      if (point.time < viewportStart || point.time > viewportStart + viewportDuration) return;
      
      const x = ((point.time - viewportStart) / viewportDuration) * canvasWidth;
      const y = canvasHeight - ((point.value - minValue) / (maxValue - minValue)) * canvasHeight;
      
      // Set point size based on hover/selected state
      const isHovered = index === hoveredPointIndex;
      const isSelected = index === selectedPointIndex;
      const pointRadius = isHovered ? 10 : 6; // Bigger on hover
      
      ctx.beginPath();
      ctx.fillStyle = isSelected ? '#3182ce' : (isHovered ? '#63b3ed' : '#4299e1');
      ctx.arc(x, y, pointRadius, 0, Math.PI * 2);
      ctx.fill();
      
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.stroke();
    });
  }
  
  // Helper function to calculate appropriate grid step based on viewport duration
  function calculateGridStep(viewportDuration) {
    if (viewportDuration <= 10) return 1; // Every second
    if (viewportDuration <= 30) return 5; // Every 5 seconds
    if (viewportDuration <= 60) return 10; // Every 10 seconds
    if (viewportDuration <= 180) return 30; // Every 30 seconds
    return 60; // Every minute
  }
  
  // Function to format time for display (MM:SS)
  function formatTime(timeInSeconds) {
    const minutes = Math.floor(timeInSeconds / 60);
    const seconds = Math.floor(timeInSeconds % 60);
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  }
  
  // Watch for duration changes
  $: if (duration) {
    // Update the last point if it was at the end of the timeline
    const lastPoint = envelopePoints.find(p => p.time === envelopePoints.sort((a, b) => b.time - a.time)[0].time);
    if (lastPoint && Math.abs(lastPoint.time - (duration - viewportDuration)) < 1) {
      lastPoint.time = duration;
      redrawCanvas();
    }
  }
  
  // Watch for changes to viewportStart or viewportDuration
  $: if (viewportStart !== undefined || viewportDuration !== undefined) {
    redrawCanvas();
  }
  
  onMount(() => {
    if (canvasRef) {
      const resizeObserver = new ResizeObserver(entries => {
        for (let entry of entries) {
          const { width, height } = entry.contentRect;
          canvasWidth = width;
          canvasHeight = height;
          canvasRef.width = width;
          canvasRef.height = height;
          redrawCanvas();
        }
      });
      
      resizeObserver.observe(canvasRef.parentElement);
      
      return () => {
        resizeObserver.disconnect();
      };
    }
  });
  
  // Watch for parameter change
  $: if (currentParam) {
    initializePoints();
  }
  
  // Redraw when time changes
  $: if (currentTime !== undefined) {
    redrawCanvas();
  }
</script>

<div class="w-full bg-white rounded-lg shadow-lg p-4">
  <div class="flex items-center justify-between mb-4">
    <div class="flex items-center gap-4">
      <label for="paramSelect" class="text-sm font-medium text-gray-700">Parameter:</label>
      <select 
        id="paramSelect"
        class="px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
        bind:value={currentParam}
      >
        <option value="gravity">Gravity</option>
        <option value="density">Density</option>
        <option value="wind_x">Wind X</option>
        <option value="wind_y">Wind Y</option>
        <option value="wind_z">Wind Z</option>
        <option value="viscosity">Viscosity</option>
        <option value="integrator">Integrator</option>
        <option value="timestep">Timestep</option>
      </select>
    </div>
    
    <div class="text-sm text-gray-600">
      Current Value: {$parameterStore[currentParam]?.toFixed(2) || '0.00'}
    </div>
  </div>

  <div class="w-full h-48 bg-gray-50 rounded border border-gray-200 relative">
    <canvas
      bind:this={canvasRef}
      class="w-full h-full cursor-crosshair"
      on:mousedown={handleMouseDown}
      on:contextmenu={handleContextMenu}
      on:mousemove={handleMouseMove}
      on:mouseup={handleMouseUp}
      on:mouseleave={handleMouseUp}
    ></canvas>
  </div>
  
  <div class="mt-2 text-xs text-gray-500">
    <p>Click to add points. Click and drag to move points. Right-click to delete a point. First and last points can only move vertically.</p>
  </div>
</div>