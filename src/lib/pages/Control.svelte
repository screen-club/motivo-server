<script>
  import { onMount } from 'svelte';
  import LiveFeed from '../components/LiveFeed.svelte';

  let socket;
  let parameters = {
    gravity: -9.81,
    density: 1.2,
    wind_x: 0.0,
    wind_y: 0.0,
    wind_z: 0.0,
    viscosity: 0.0,
    integrator: 0,
    timestep: 0.002
  };

  function connectWebSocket() {
    socket = new WebSocket('ws://localhost:8765');
    
    socket.onopen = () => {
      console.log('WebSocket connected');
      // Request current parameters
      socket.send(JSON.stringify({
        type: "get_parameters",
        timestamp: new Date().toISOString()
      }));
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "parameters") {
        parameters = data.parameters;
      }
    };

    socket.onclose = () => {
      console.log('WebSocket disconnected');
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  function sendParameters() {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: "update_parameters",
        parameters: parameters,
        timestamp: new Date().toISOString()
      }));
    }
  }

  onMount(() => {
    connectWebSocket();
    return () => {
      if (socket) socket.close();
    };
  });
</script>

<div class="flex gap-4">
  <div class="w-96 py-4">
    <div class="bg-white rounded-lg shadow-lg p-4">
      <h1 class="text-lg font-bold mb-4 text-gray-800">Environment Parameters</h1>
      
      <div class="space-y-3">
        <!-- Gravity & Density -->
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-700">
              Gravity: {parameters.gravity}
            </label>
            <input 
              type="range" 
              bind:value={parameters.gravity} 
              min="-30" max="0" step="0.1"
              on:change={sendParameters}
              class="w-full h-1 bg-gray-200 rounded-lg appearance-none cursor-pointer"
            />
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-700">
              Density: {parameters.density}
            </label>
            <input 
              type="range" 
              bind:value={parameters.density} 
              min="0" max="5" step="0.1"
              on:change={sendParameters}
              class="w-full h-1 bg-gray-200 rounded-lg appearance-none cursor-pointer"
            />
          </div>
        </div>

        <!-- Wind Controls -->
        <div class="bg-gray-50 p-2 rounded-lg space-y-2">
          <h2 class="text-xs font-semibold text-gray-700">Wind Controls</h2>
          <div class="grid grid-cols-3 gap-2">
            {#each ['x', 'y', 'z'] as axis}
              <div class="space-y-1">
                <label class="block text-xs font-medium text-gray-700">
                  {axis}: {parameters[`wind_${axis}`]}
                </label>
                <input 
                  type="range" 
                  bind:value={parameters[`wind_${axis}`]} 
                  min="-10" max="10" step="0.1"
                  on:change={sendParameters}
                  class="w-full h-1 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                />
              </div>
            {/each}
          </div>
        </div>

        <!-- Viscosity & Timestep -->
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-700">
              Viscosity: {parameters.viscosity}
            </label>
            <input 
              type="range" 
              bind:value={parameters.viscosity} 
              min="0" max="1" step="0.01"
              on:change={sendParameters}
              class="w-full h-1 bg-gray-200 rounded-lg appearance-none cursor-pointer"
            />
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-700">
              Timestep: {parameters.timestep}
            </label>
            <input 
              type="range" 
              bind:value={parameters.timestep} 
              min="0.001" max="0.01" step="0.001"
              on:change={sendParameters}
              class="w-full h-1 bg-gray-200 rounded-lg appearance-none cursor-pointer"
            />
          </div>
        </div>

        <!-- Integrator -->
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">
            Integrator
          </label>
          <select 
            bind:value={parameters.integrator} 
            on:change={sendParameters}
            class="block w-full text-sm rounded border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
          >
            <option value={0}>Euler</option>
            <option value={1}>RK4</option>
          </select>
        </div>

        <button 
          on:click={() => {
            parameters = {
              gravity: -9.81,
              density: 1.2,
              wind_x: 0.0,
              wind_y: 0.0,
              wind_z: 0.0,
              viscosity: 0.0,
              integrator: 0,
              timestep: 0.002
            };
            sendParameters();
          }}
          class="w-full bg-gray-600 text-white px-3 py-1 text-sm rounded hover:bg-gray-700 transition-colors"
        >
          Reset to Defaults
        </button>
      </div>
    </div>
  </div>

  <div class="flex-grow">
    <LiveFeed />
  </div>
</div> 