<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { parameterStore } from '../../stores/parameterStore';
  
  // Props
  export let currentParam = null;
  export let duration = 180;
  export let viewportStart = 0;
  export let viewportDuration = 180;

  // LFO properties
  let waveform = 'sine'; // 'sine', 'square', 'triangle'
  let frequency = 0.1; // cycles per second
  let amplitude = 0.5; // percentage of min/max range
  let offset = 0.5; // center point (0.0 to 1.0)
  let phase = 0; // phase offset in degrees (0-360)
  
  // Canvas for preview
  let canvasRef;
  let canvasWidth = 0;
  let canvasHeight = 0;
  let previewCurve = [];

  const dispatch = createEventDispatcher();
  
  // Get parameter bounds
  $: paramBounds = currentParam && $parameterStore ? getParameterBounds(currentParam) : { min: 0, max: 1 };
  
  // The parameter bounds remain the same as in the PresetTimelineEnvelope component
  function getParameterBounds(param) {
    const bounds = {
      gravity: { min: -100, max: 0 },
      density: { min: 0, max: 5 },
      wind_x: { min: -20, max: 20 },
      wind_y: { min: -20, max: 20 },
      wind_z: { min: -20, max: 20 },
      viscosity: { min: 0, max: 10 },
      integrator: { min: 0, max: 2 },
      timestep: { min: 0.0001, max: 0.01 }
    };
    
    return bounds[param] || { min: 0, max: 1 };
  }
  
  // Generate the LFO curve
  function generateLFOCurve() {
    if (!currentParam) return null;
    
    const points = [];
    const range = paramBounds.max - paramBounds.min;
    const centerValue = paramBounds.min + (range * offset);
    const amplitudeValue = range * amplitude;
    const phaseRadians = (phase * Math.PI) / 180;
    
    // Generate at least 20 points for a smooth curve
    const numPoints = Math.max(20, Math.min(100, Math.floor(duration * frequency * 10)));
    
    for (let i = 0; i <= numPoints; i++) {
      const time = (i / numPoints) * duration;
      const normalizedTime = (time / duration) * (frequency * duration) * 2 * Math.PI + phaseRadians;
      
      let value;
      switch (waveform) {
        case 'sine':
          value = centerValue + amplitudeValue * Math.sin(normalizedTime);
          break;
        case 'square':
          value = centerValue + amplitudeValue * (Math.sin(normalizedTime) >= 0 ? 1 : -1);
          break;
        case 'triangle':
          value = centerValue + amplitudeValue * (2 * Math.asin(Math.sin(normalizedTime)) / Math.PI);
          break;
        default:
          value = centerValue;
      }
      
      // Clamp value to parameter bounds
      value = Math.max(paramBounds.min, Math.min(paramBounds.max, value));
      
      points.push({ time, value });
    }
    
    return { [currentParam]: points };
  }
  
  // Update preview without applying
  function updatePreview() {
    const envelope = generateLFOCurve();
    if (envelope && currentParam) {
      previewCurve = envelope[currentParam];
      redrawCanvas();
    }
  }
  
  // Apply the LFO curve to the envelope
  function applyLFO() {
    const envelope = generateLFOCurve();
    if (envelope) {
      dispatch('lfoGenerated', { envelope });
    }
  }
  
  // Draw the preview curve on the canvas
  function redrawCanvas() {
    if (!canvasRef || !previewCurve || previewCurve.length === 0) return;
    
    const ctx = canvasRef.getContext('2d');
    ctx.clearRect(0, 0, canvasWidth, canvasHeight);
    
    // Draw background grid (similar to envelope component)
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
    }
    
    // Horizontal grid lines
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const y = (i / steps) * canvasHeight;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvasWidth, y);
      ctx.stroke();
      
      // Label the values (same as in envelope component)
      const value = paramBounds.max - ((i / steps) * (paramBounds.max - paramBounds.min));
      ctx.fillStyle = '#718096';
      ctx.font = '10px sans-serif';
      ctx.fillText(value.toFixed(1), 5, y - 2);
    }
    
    // Draw the LFO curve
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(100, 100, 100, 0.7)'; // Grey color with transparency
    ctx.lineWidth = 2;
    
    let started = false;
    
    previewCurve.forEach((point, index) => {
      // Use same calculations as in PresetTimelineEnvelope
      const x = ((point.time - viewportStart) / viewportDuration) * canvasWidth;
      const y = canvasHeight - ((point.value - paramBounds.min) / (paramBounds.max - paramBounds.min)) * canvasHeight;
      
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    
    ctx.stroke();
    
    // Add a label
    ctx.fillStyle = 'rgba(100, 100, 100, 0.7)';
    ctx.font = '11px sans-serif';
    ctx.fillText('LFO Preview', 5, 12);
  }
  
  // Helper function to calculate appropriate grid step based on viewport duration
  // Copied from PresetTimelineEnvelope for consistency
  function calculateGridStep(viewportDuration) {
    if (viewportDuration <= 10) return 1; // Every second
    if (viewportDuration <= 30) return 5; // Every 5 seconds
    if (viewportDuration <= 60) return 10; // Every 10 seconds
    if (viewportDuration <= 180) return 30; // Every 30 seconds
    return 60; // Every minute
  }
  
  // Auto-update preview when parameters change
  $: {
    if (waveform && frequency && amplitude && offset && currentParam) {
      updatePreview();
    }
  }
  
  // Update when viewport or parameter changes
  $: if (viewportStart !== undefined || viewportDuration !== undefined || currentParam) {
    updatePreview();
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
  
  // Update preview on mount
  onMount(updatePreview);
</script>

<div class="w-full bg-white rounded-lg shadow-md p-4 mb-4">
  <h3 class="text-sm font-medium text-gray-700 mb-3">LFO Generator</h3>
  
  <!-- Preview Canvas -->
  <div class="w-full h-24 bg-gray-50 rounded border border-gray-200 relative mb-3">
    <canvas
      bind:this={canvasRef}
      class="w-full h-full"
    ></canvas>
  </div>
  
  <div class="grid grid-cols-1 gap-3">
    <!-- Waveform Selector -->
    <div class="flex items-center justify-between">
      <span class="text-xs text-gray-600">Waveform:</span>
      <div class="flex gap-2">
        <button 
          class="p-2 rounded {waveform === 'sine' ? 'bg-blue-100 border-blue-300' : 'bg-gray-50 border-gray-200'} border"
          on:click={() => waveform = 'sine'}
          title="Sine Wave"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12 C7 6, 11 18, 15 12, 19 6, 23 12" />
          </svg>
        </button>
        <button 
          class="p-2 rounded {waveform === 'square' ? 'bg-blue-100 border-blue-300' : 'bg-gray-50 border-gray-200'} border"
          on:click={() => waveform = 'square'}
          title="Square Wave"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12 L7 12 L7 6 L11 6 L11 18 L15 18 L15 6 L19 6 L19 18 L23 18" />
          </svg>
        </button>
        <button 
          class="p-2 rounded {waveform === 'triangle' ? 'bg-blue-100 border-blue-300' : 'bg-gray-50 border-gray-200'} border"
          on:click={() => waveform = 'triangle'}
          title="Triangle Wave"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12 L7 6 L11 18 L15 6 L19 18 L23 12" />
          </svg>
        </button>
      </div>
    </div>
    
    <!-- Frequency -->
    <div>
      <div class="flex justify-between">
        <label for="frequency" class="text-xs text-gray-600">Frequency:</label>
        <span class="text-xs text-gray-500">{frequency.toFixed(2)} Hz</span>
      </div>
      <input 
        id="frequency" 
        type="range" 
        min="0.01" 
        max="1" 
        step="0.01" 
        bind:value={frequency} 
        class="w-full"
      />
    </div>
    
    <!-- Amplitude -->
    <div>
      <div class="flex justify-between">
        <label for="amplitude" class="text-xs text-gray-600">Amplitude:</label>
        <span class="text-xs text-gray-500">{(amplitude * 100).toFixed(0)}%</span>
      </div>
      <input 
        id="amplitude" 
        type="range" 
        min="0" 
        max="1" 
        step="0.01" 
        bind:value={amplitude} 
        class="w-full"
      />
    </div>
    
    <!-- Offset -->
    <div>
      <div class="flex justify-between">
        <label for="offset" class="text-xs text-gray-600">Center Point:</label>
        <span class="text-xs text-gray-500">{offset.toFixed(2)}</span>
      </div>
      <input 
        id="offset" 
        type="range" 
        min="0" 
        max="1" 
        step="0.01" 
        bind:value={offset} 
        class="w-full"
      />
    </div>
    
    <!-- Phase -->
    <div>
      <div class="flex justify-between">
        <label for="phase" class="text-xs text-gray-600">Phase:</label>
        <span class="text-xs text-gray-500">{phase}°</span>
      </div>
      <input 
        id="phase" 
        type="range" 
        min="0" 
        max="360" 
        step="15" 
        bind:value={phase} 
        class="w-full"
      />
    </div>
    
    <!-- Apply Button -->
    <button 
      class="mt-2 w-full bg-blue-500 hover:bg-blue-600 text-white py-2 px-4 rounded transition"
      on:click={applyLFO}
    >
      Apply LFO to {currentParam || 'current parameter'}
    </button>
  </div>
</div>