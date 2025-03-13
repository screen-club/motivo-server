<script>
  import { REWARD_TYPES } from '../../stores/rewardStore';
  import ParameterControl from '../parameters/ParameterControl.svelte';
  import ParameterGroup from '../parameters/ParameterGroup.svelte';
  import { fade } from 'svelte/transition';
  import { formatParameterLabel } from './RewardTypes';
  
  export let reward;
  export let index;
  export let weight;
  export let onWeightChange;
  export let onUpdate;
  export let onRemove;
  
  let pendingChanges = {};
  let isEditing = false;
  
  function handleParameterChange(event) {
    const { name, value } = event.detail;
    pendingChanges[name] = value;
    isEditing = Object.keys(pendingChanges).length > 0;
  }
  
  function updateReward() {
    if (Object.keys(pendingChanges).length > 0) {
      onUpdate(pendingChanges);
      pendingChanges = {};
      isEditing = false;
    }
  }
  
  function discardChanges() {
    pendingChanges = {};
    isEditing = false;
  }
</script>

<div class="border rounded-md p-4 bg-white flex flex-col" transition:fade>
  <!-- Header with name and weight -->
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-lg font-bold text-blue-600">
      {reward.name}
    </h3>
    <div class="flex items-center gap-2">
      <span class="text-xs text-gray-500">Weight</span>
      <div class="w-24">
        <ParameterControl
          name="weight"
          type="range"
          value={weight * 100}
          min={0}
          max={100}
          step={1}
          on:change={(e) => onWeightChange(e.detail.value / 100)}
        />
      </div>
    </div>
  </div>

  <!-- Divider -->
  <div class="h-px bg-gray-200 -mx-4 mb-3"></div>

  <!-- Parameters -->
  <div class="space-y-3 flex-1">
    <ParameterGroup columns={2}>
      {#each Object.entries(reward).filter(([key]) => !['id', 'name'].includes(key)) as [param, value]}
        {#if REWARD_TYPES[reward.name]?.[param]}
          <ParameterControl
            name={param}
            label={formatParameterLabel(param)}
            type={REWARD_TYPES[reward.name][param].type}
            min={REWARD_TYPES[reward.name][param].min}
            max={REWARD_TYPES[reward.name][param].max}
            step={REWARD_TYPES[reward.name][param].step}
            options={REWARD_TYPES[reward.name][param].options?.map(opt => ({ value: opt, label: opt }))}
            value={pendingChanges[param] !== undefined ? pendingChanges[param] : value}
            on:change={handleParameterChange}
          />
        {/if}
      {/each}
    </ParameterGroup>
  </div>

  <!-- Action buttons -->
  <div class="flex justify-end gap-2 mt-auto pt-3">
    {#if isEditing}
      <button 
        class="bg-gray-200 text-gray-700 px-2 py-1 text-xs rounded hover:bg-gray-300"
        on:click={discardChanges}
      >
        Cancel
      </button>
      <button 
        class="bg-blue-500 text-white px-3 py-1 text-xs font-medium rounded hover:bg-blue-600"
        on:click={updateReward}
      >
        Update
      </button>
    {:else}
      <button 
        class="bg-red-50 text-red-600 px-2 py-1 text-xs font-medium rounded hover:bg-red-100"
        on:click={() => onRemove()}
      >
        Remove
      </button>
    {/if}
  </div>
</div>