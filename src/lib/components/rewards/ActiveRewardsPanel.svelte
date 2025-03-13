<script>
  import { onMount, onDestroy } from 'svelte';
  import { websocketService } from '../../services/websocket';
  import { favoriteStore } from '../../stores/favoriteStore';
  import RewardCard from './RewardCard.svelte';
  import { COMBINATION_TYPES } from './RewardTypes';

  let activeRewards = null;
  let cleanupHandler;

  onMount(() => {
    cleanupHandler = websocketService.addMessageHandler((data) => {
      if (data.type === 'debug_model_info') {
        activeRewards = data.active_rewards;
      }
    });

    // Request initial state
    websocketService.getSocket()?.send(JSON.stringify({
      type: "debug_model_info"
    }));
  });

  onDestroy(() => {
    if (cleanupHandler) cleanupHandler();
  });

  function handleWeightChange(rewardIndex, newWeight) {
    if (!activeRewards) return;
    
    // Create a copy of the current weights array
    const newWeights = [...activeRewards.weights];
    newWeights[rewardIndex] = newWeight;
    
    // Send immediate weight update
    websocketService.getSocket()?.send(JSON.stringify({
      type: 'request_reward',
      reward: {
        ...activeRewards,
        weights: newWeights
      },
      timestamp: new Date().toISOString()
    }));
  }

  function updateReward(rewardIndex, updatedParams) {
    if (!activeRewards) return;
    websocketService.updateReward(rewardIndex, updatedParams);
  }

  function removeReward(rewardIndex) {
    if (!activeRewards) return;
    
    const updatedRewards = {
      ...activeRewards,
      rewards: activeRewards.rewards.filter((_, idx) => idx !== rewardIndex),
      weights: activeRewards.weights.filter((_, idx) => idx !== rewardIndex)
    };
    
    websocketService.getSocket()?.send(JSON.stringify({
      type: 'request_reward',
      reward: updatedRewards,
      timestamp: new Date().toISOString()
    }));
  }

  function saveCurrentConfig() {
    const name = prompt('Enter a name for this configuration:');
    if (!name || !activeRewards) return;
    
    // Format the rewards data to include weights
    const rewardsWithWeights = activeRewards.rewards.map((reward, index) => ({
      ...reward,
      weight: activeRewards.weights[index]
    }));

    // Save to favoriteStore
    favoriteStore.saveFavorite(name, {
      activeRewards: rewardsWithWeights,
      combinationType: activeRewards.combinationType
    });
  }

  function handleCombinationTypeChange(event) {
    const newCombinationType = event.target.value;
    if (activeRewards) {
      websocketService.getSocket()?.send(JSON.stringify({
        type: 'request_reward',
        reward: {
          ...activeRewards,
          combinationType: newCombinationType
        },
        timestamp: new Date().toISOString()
      }));
    }
  }
</script>

<div class="bg-white rounded-lg shadow-sm p-4 h-full flex flex-col">
  <div class="flex justify-between items-center mb-4">
    <h2 class="text-lg font-semibold">Active Rewards</h2>
    {#if activeRewards?.rewards?.length > 0}
      <button 
        class="bg-green-600 hover:bg-green-700 text-white px-3 py-1 text-sm font-medium rounded-md transition-colors"
        on:click={saveCurrentConfig}
      >
        Save Configuration
      </button>
    {/if}
  </div>
  
  {#if activeRewards?.rewards?.length > 0}
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 flex-1 overflow-y-auto">
      {#each activeRewards.rewards as reward, index}
        <RewardCard 
          {reward}
          {index}
          weight={activeRewards.weights[index]}
          onWeightChange={(newWeight) => handleWeightChange(index, newWeight)}
          onUpdate={(changes) => updateReward(index, changes)}
          onRemove={() => removeReward(index)}
        />
      {/each}
    </div>
    
    <div class="mt-4 pt-3 border-t border-gray-100">
      <div class="flex items-center gap-2">
        <label for="combination-type" class="text-sm font-medium text-gray-700">Combination Type:</label>
        <select 
          id="combination-type"
          class="text-sm rounded border border-gray-300 bg-white px-2 py-1"
          value={activeRewards.combinationType}
          on:change={handleCombinationTypeChange}
        >
          {#each COMBINATION_TYPES as type}
            <option value={type.value}>{type.label}</option>
          {/each}
        </select>
      </div>
    </div>
  {:else}
    <div class="flex-1 flex items-center justify-center">
      <p class="text-gray-500 italic">No active rewards. Add a reward from the left panel.</p>
    </div>
  {/if}
</div>