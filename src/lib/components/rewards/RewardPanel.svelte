<script>
  import { websocketService } from '../../services/websocket';
  import ParameterControl from '../parameters/ParameterControl.svelte';
  import ParameterGroup from '../parameters/ParameterGroup.svelte';
  import { v4 as uuidv4 } from 'uuid';
  import { REWARD_TYPES } from '../../stores/rewardStore';
  import { REWARD_GROUPS, initializeParameters } from './RewardTypes';

  let selectedGroup = Object.keys(REWARD_GROUPS)[0];
  let selectedRewardType = REWARD_GROUPS[selectedGroup][0];
  let activeParameters = initializeParameters(selectedRewardType);
  let addMode = true; // true = add to existing, false = replace all

  // Watch for group changes and update reward type accordingly
  $: {
    if (!REWARD_GROUPS[selectedGroup].includes(selectedRewardType)) {
      selectedRewardType = REWARD_GROUPS[selectedGroup][0];
    }
  }

  // Reset parameters when reward type changes
  $: activeParameters = initializeParameters(selectedRewardType);

  // Handle parameter changes
  function handleParameterChange(param, value) {
    activeParameters = {
      ...activeParameters,
      [param]: value
    };
  }

  // Add selected reward to active rewards
  function addReward() {
    const addToExisting = addMode;
    const rewardId = uuidv4();
    const newReward = {
      id: rewardId,
      name: selectedRewardType,
      ...activeParameters
    };

    // Send reward through websocket
    const ws = websocketService.getSocket();
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'request_reward',
        reward: {
          rewards: [newReward],
          weights: [1.0],
          combinationType: 'geometric'
        },
        add_to_existing: addToExisting,
        timestamp: new Date().toISOString()
      }));

      // Request updated state
      setTimeout(() => {
        ws.send(JSON.stringify({
          type: "debug_model_info"
        }));
      }, 100);
    }
  }
</script>

<div class="w-full bg-white rounded-lg shadow-sm p-4">
  <h2 class="text-lg font-semibold mb-4">Add Reward</h2>
  
  <div class="space-y-4">
    <!-- Group Selection -->
    <div class="mb-3">
      <label for="reward-group" class="block text-sm font-medium text-gray-700 mb-1">Reward Group</label>
      <select
        id="reward-group"
        bind:value={selectedGroup}
        class="block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6"
      >
        {#each Object.keys(REWARD_GROUPS) as group}
          <option value={group}>{group}</option>
        {/each}
      </select>
    </div>

    <!-- Reward Type Selection -->
    <div class="mb-3">
      <label for="reward-type" class="block text-sm font-medium text-gray-700 mb-1">Reward Type</label>
      <select
        id="reward-type"
        bind:value={selectedRewardType}
        class="block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6"
      >
        {#each REWARD_GROUPS[selectedGroup] as type}
          <option value={type}>{type}</option>
        {/each}
      </select>
    </div>

    <!-- Parameters Section -->
    <div class="bg-gray-50 p-3 rounded-md">
      <h3 class="text-sm font-medium text-gray-700 mb-2">Parameters</h3>
      <ParameterGroup>
        {#each Object.entries(REWARD_TYPES[selectedRewardType]) as [param, config]}
          <ParameterControl
            name={param}
            label={param.replace(/_/g, ' ')}
            type={config.type}
            min={config.min}
            max={config.max}
            step={config.step}
            options={config.options?.map(opt => ({ value: opt, label: opt }))}
            value={activeParameters[param]}
            on:change={({ detail }) => handleParameterChange(detail.name, detail.value)}
          />
        {/each}
      </ParameterGroup>
    </div>

    <!-- Mode selection -->
    <div class="flex items-center space-x-4 mb-3">
      <label class="inline-flex items-center cursor-pointer">
        <input type="radio" name="add-mode" bind:group={addMode} value={true} class="form-radio h-4 w-4 text-blue-600">
        <span class="ml-2 text-sm text-gray-700">Add to existing</span>
      </label>
      <label class="inline-flex items-center cursor-pointer">
        <input type="radio" name="add-mode" bind:group={addMode} value={false} class="form-radio h-4 w-4 text-blue-600">
        <span class="ml-2 text-sm text-gray-700">Replace all</span>
      </label>
    </div>

    <button
      on:click={addReward}
      class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-md transition-colors"
    >
      {addMode ? 'Add Reward' : 'Replace All Rewards'}
    </button>
  </div>
</div>