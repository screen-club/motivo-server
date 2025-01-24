<script>
  import { rewardStore, REWARD_TYPES, COMBINATION_TYPES } from '../stores/rewardStore';
  import ParameterControl from './ParameterControl.svelte';
  import ParameterGroup from './ParameterGroup.svelte';

  const REWARD_GROUPS = {
    'Basic Movements': ['move-ego', 'jump', 'rotation', 'crawl'],
    'Poses': ['raisearms', 'headstand', 'liedown', 'sit', 'split'],
    'Combined Actions': ['move-and-raise-arms'],
    'Hand Controls': [
      'left-hand-height', 'left-hand-lateral', 'left-hand-forward',
      'right-hand-height', 'right-hand-lateral', 'right-hand-forward',
      'hand-height', 'hand-lateral'
    ],
    'Foot Controls': [
      'left-foot-height', 'right-foot-height',
      'left-foot-lateral', 'right-foot-lateral',
      'left-foot-forward', 'right-foot-forward'
    ],
    'Other Controls': [
      'stay-upright', 'head-height', 'pelvis-height'
    ]
  };

  let selectedGroup = Object.keys(REWARD_GROUPS)[0];
  let selectedRewardType = REWARD_GROUPS[selectedGroup][0];
  let currentParameters = {};

  $: {
    // Reset parameters when reward type changes
    currentParameters = Object.fromEntries(
      Object.entries(REWARD_TYPES[selectedRewardType]).map(
        ([key, config]) => [key, config.default]
      )
    );
  }

  function addReward() {
    rewardStore.addReward(selectedRewardType, currentParameters);
  }

  // Update selected reward type when group changes
  $: {
    if (!REWARD_GROUPS[selectedGroup].includes(selectedRewardType)) {
      selectedRewardType = REWARD_GROUPS[selectedGroup][0];
    }
  }
</script>

<div class="w-96 py-4">
  <div class="bg-white rounded-lg shadow-lg p-4">
    <h1 class="text-lg font-bold mb-4 text-gray-800">Reward Controls</h1>
    
    <!-- Active Rewards -->
    {#if $rewardStore.activeRewards.length > 0}
      <div class="mb-4">
        <h2 class="text-sm font-semibold mb-2">Active Rewards</h2>
        {#each $rewardStore.activeRewards as reward, i}
          <div class="flex items-center gap-2 mb-2 bg-gray-50 p-2 rounded">
            <div class="flex-grow">
              <div class="text-sm font-medium">{reward.name}</div>
              <div class="text-xs text-gray-500">
                Weight: 
                <input 
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={$rewardStore.weights[i]}
                  on:input={(e) => rewardStore.updateWeight(i, parseFloat(e.target.value))}
                  class="w-24 inline-block"
                />
                {($rewardStore.weights[i] * 100).toFixed(0)}%
              </div>
            </div>
            <button
              on:click={() => rewardStore.removeReward(i)}
              class="text-red-500 hover:text-red-700"
            >
              ×
            </button>
          </div>
        {/each}

        <select
          bind:value={$rewardStore.combinationType}
          class="mt-2 block w-full text-sm rounded border-gray-300"
        >
          {#each COMBINATION_TYPES as type}
            <option value={type}>{type}</option>
          {/each}
        </select>

        <button
          on:click={() => rewardStore.cleanRewards()}
          class="mt-2 w-full bg-red-600 text-white px-3 py-1 text-sm rounded hover:bg-red-700"
        >
          Clear All Rewards
        </button>
      </div>
    {/if}

    <!-- Add New Reward -->
    <div class="space-y-3">
      <!-- Group Selection -->
      <select
        bind:value={selectedGroup}
        class="block w-full text-sm rounded border-gray-300"
      >
        {#each Object.keys(REWARD_GROUPS) as group}
          <option value={group}>{group}</option>
        {/each}
      </select>

      <!-- Reward Type Selection -->
      <select
        bind:value={selectedRewardType}
        class="block w-full text-sm rounded border-gray-300"
      >
        {#each REWARD_GROUPS[selectedGroup] as type}
          <option value={type}>{type}</option>
        {/each}
      </select>

      <ParameterGroup>
        {#each Object.entries(REWARD_TYPES[selectedRewardType]) as [param, config]}
          <ParameterControl
            name={param}
            label={param}
            type={config.type}
            min={config.min}
            max={config.max}
            step={config.step}
            options={config.options?.map(opt => ({ value: opt, label: opt }))}
            bind:value={currentParameters[param]}
          />
        {/each}
      </ParameterGroup>

      <button
        on:click={addReward}
        class="w-full bg-blue-600 text-white px-3 py-1 text-sm rounded hover:bg-blue-700"
      >
        Add Reward
      </button>
    </div>
  </div>
</div> 