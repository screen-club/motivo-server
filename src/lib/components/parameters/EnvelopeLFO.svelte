<script>
  import { createEventDispatcher } from 'svelte';
  import { parameterStore } from '../../stores/parameterStore';
  
  // Props
  export let currentParam = null;
  export let duration = 180;

  // LFO properties
  let waveform = 'sine'; // 'sine', 'square', 'triangle'
  let frequency = 0.1; // cycles per second
  let amplitude = 0.5; // percentage of min/max range
  let offset = 0.5; // center point (0.0 to 1.0)
  let phase = 0; // phase offset in degrees (0-360)

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
    if (!currentParam) return;
    
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
  
  // Apply the LFO curve to the envelope
  function applyLFO() {
    const envelope = generateLFOCurve();
    if (envelope) {
      dispatch('lfoGenerated', { envelope });
    }
  }
  
  // Auto-generate when parameters change
  $: {
    if (waveform && frequency && amplitude && offset && currentParam) {
      applyLFO();
    }
  }
</script>

<div class="w-full bg-white rounded-lg shadow-md p-4 mb-4">
  <h3 class="text-sm font-medium text-gray-700 mb-3">LFO Generator</h3>
  
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
      Apply LFO
    </button>
  </div>
</div>