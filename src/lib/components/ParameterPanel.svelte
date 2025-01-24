<script>
  import { parameterStore } from '../stores/parameterStore';
  import ParameterControl from './ParameterControl.svelte';
  import ParameterGroup from './ParameterGroup.svelte';
</script>

<div class="w-96 py-4">
  <div class="bg-white rounded-lg shadow-lg p-4">
    <h1 class="text-lg font-bold mb-4 text-gray-800">Environment Parameters</h1>
    
    <div class="space-y-3">
      <!-- Basic Parameters -->
      <ParameterGroup columns={2}>
        <ParameterControl
          name="gravity"
          label="Gravity"
          type="range"
          min="-30"
          max="0"
          step="0.1"
        />
        <ParameterControl
          name="density"
          label="Density"
          type="range"
          min="0"
          max="5"
          step="0.1"
        />
      </ParameterGroup>

      <!-- Wind Controls -->
      <ParameterGroup title="Wind Controls" columns={3}>
        {#each ['x', 'y', 'z'] as axis}
          <ParameterControl
            name={`wind_${axis}`}
            label={axis.toUpperCase()}
            type="range"
            min="-10"
            max="10"
            step="0.1"
          />
        {/each}
      </ParameterGroup>

      <!-- Additional Parameters -->
      <ParameterGroup columns={2}>
        <ParameterControl
          name="viscosity"
          label="Viscosity"
          type="range"
          min="0"
          max="1"
          step="0.01"
        />
        <ParameterControl
          name="timestep"
          label="Timestep"
          type="range"
          min="0.001"
          max="0.01"
          step="0.001"
        />
      </ParameterGroup>

      <!-- Integrator -->
      <ParameterGroup layout="stack">
        <ParameterControl
          name="integrator"
          label="Integrator"
          type="select"
          options={[
            { value: 0, label: 'Euler' },
            { value: 1, label: 'RK4' }
          ]}
        />
      </ParameterGroup>

      <button 
        on:click={() => parameterStore.reset()}
        class="w-full bg-gray-600 text-white px-3 py-1 text-sm rounded hover:bg-gray-700 transition-colors"
      >
        Reset to Defaults
      </button>
    </div>
  </div>
</div> 