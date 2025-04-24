<script>
  import { parameterStore } from '../../stores/parameterStore';
  import { websocketService } from '../../services/websocket';
  import ParameterControl from './ParameterControl.svelte';
  import ParameterGroup from './ParameterGroup.svelte';
  // Remove envelope button for simplification
  //import ParameterEnvelopeButton from './ParameterEnvelopeButton.svelte';

  let { class: className = '', isCompact = false } = $props();

  // Subscribe to the store values
  let parameters = $derived($parameterStore);

  function handleParameterChange(event) {
    const { name, value } = event.detail;
    parameterStore.updateParameter(name, value);
  }

  function resetSimulation() {
    const socket = websocketService.getSocket();
    if (socket) {
      socket.send(JSON.stringify({ type: "clean_rewards" }));
    }
  }
</script>

<div class="w-full {className}" class:py-2={!isCompact}>
  <div class="bg-white rounded-lg shadow-sm" class:p-4={!isCompact} class:p-1={isCompact}>
    <h2 
      class="font-semibold" 
      class:text-lg={!isCompact} class:mb-4={!isCompact}
      class:text-xs={isCompact} class:mb-1={isCompact}
      class:hidden={isCompact}
    >Environment Parameters</h2>
    
    <div class="" class:space-y-4={!isCompact} class:space-y-1={isCompact}>
      <!-- Basic Parameters -->
      <ParameterGroup columns={2} {isCompact}>
        <ParameterControl
          name="gravity"
          label="Gravity"
          type="range"
          min={-30}
          max={0}
          step={0.1}
          value={parameters.gravity}
          defaultValue={-9.81}
          on:change={handleParameterChange}
          {isCompact}
        />

        <ParameterControl
          name="density"
          label="Density"
          type="range"
          min={0}
          max={5}
          step={0.1}
          value={parameters.density}
          defaultValue={1.0}
          on:change={handleParameterChange}
          {isCompact}
        />
      </ParameterGroup>

      <!-- Wind Controls -->
      <ParameterGroup title="Wind Controls" columns={3} {isCompact}>
        {#each ['x', 'y', 'z'] as axis}
          <ParameterControl
            name={`wind_${axis}`}
            label={axis.toUpperCase()}
            type="range"
            min={-100}
            max={100}
            step={0.1}
            value={parameters[`wind_${axis}`]}
            defaultValue={0}
            on:change={handleParameterChange}
            {isCompact}
          />
        {/each}
      </ParameterGroup>

      <!-- Additional Parameters -->
      <ParameterGroup columns={2} {isCompact}>
        <ParameterControl
          name="viscosity"
          label="Viscosity"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={parameters.viscosity}
          defaultValue={0.1}
          on:change={handleParameterChange}
          {isCompact}
        />
        <ParameterControl
          name="timestep"
          label="Timestep"
          type="range"
          min={0.0001}
          max={0.002}
          step={0.0001}
          value={Number(parameters.timestep).toFixed(4)}
          defaultValue={0.0005}
          on:change={handleParameterChange}
          {isCompact}
        />
      </ParameterGroup>

      <div class="flex gap-2" class:mt-6={!isCompact} class:mt-1={isCompact}>
        <button 
          on:click={() => parameterStore.reset()}
          class="flex-1 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
          class:px-3={!isCompact} class:py-2={!isCompact} class:text-sm={!isCompact}
          class:px-1={isCompact} class:py-0.5={isCompact} class:text-[10px]={isCompact}
        >
          Reset Parameters
        </button>
        <button
          class="flex-1 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
          class:px-3={!isCompact} class:py-2={!isCompact} class:text-sm={!isCompact}
          class:px-1={isCompact} class:py-0.5={isCompact} class:text-[10px]={isCompact}
          on:click={resetSimulation}
        >
          Reset Simulation
        </button>
      </div>
    </div>
  </div>
</div>