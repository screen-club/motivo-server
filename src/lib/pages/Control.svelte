<script>
    import { onMount, onDestroy } from 'svelte';
    import LiveFeed from '../components/LiveFeed';
    import ParameterPanel from '../components/parameters/ParameterPanel.svelte';
    import RewardPanel from '../components/rewards/RewardPanel.svelte';
    import RecordButton from '../components/RecordButton.svelte';
    import FavoritesOverview from '../components/FavoritesOverview.svelte';
    import ActiveRewardsPanel from '../components/rewards/ActiveRewardsPanel.svelte';
    import { parameterStore } from '../stores/parameterStore';
    import { rewardStore } from '../stores/rewardStore';
    import { websocketService } from '../services/websocket';
    import VibePanel from '../components/VibePanel.svelte';
    import { favoriteStore } from '../stores/favoriteStore';
    import LLM from '../components/LLM.svelte';
    import { chatStore } from '../stores/chatStore';
    import PresetsList from '../components/presets/PresetsList.svelte';
    
    let isSocketReady = $state(false);
    let cleanupListener;
    
    // Get valid panel from localStorage or default to 'rewards'
    const storedPanel = localStorage.getItem('controlActivePanel');
    /** @type {'rewards' | 'llm'} */
    let activePanel = $state(
      storedPanel === 'rewards' || storedPanel === 'llm' ? storedPanel : 'rewards'
    );
    
    // Subscribe to favoriteStore to get the count
    let favoritesCount = $state(0);
    
    $effect(() => {
        favoritesCount = Object.keys($favoriteStore).length;
    });

    // Update localStorage when panel changes
    $effect(() => {
        // Ensure activePanel is only 'rewards' or 'llm'
        if (activePanel !== 'rewards' && activePanel !== 'llm') {
            activePanel = 'rewards';
        }
        localStorage.setItem('controlActivePanel', activePanel);
    });

    let isTestingAll = $state(false);
    let testingStatus = $state('');
    let currentStep = $state(0);
    let totalSteps = $state(0);
    
    function handleTestAll() {
        if (isTestingAll) {
            rewardStore.stopTesting();
            isTestingAll = false;
            testingStatus = '';
            currentStep = 0;
            totalSteps = 0;
        } else {
            rewardStore.startTestingAllOptions((status, step, total) => {
                testingStatus = status;
                currentStep = step;
                totalSteps = total;
            });
            isTestingAll = true;
        }
    }

    onMount(() => {
        cleanupListener = websocketService.onReadyStateChange((ready) => {
            isSocketReady = ready;
        });
        
        isSocketReady = websocketService.getSocket()?.readyState === WebSocket.OPEN;
    });
    
    onDestroy(() => {
        if (cleanupListener) cleanupListener();
        rewardStore.stopTesting(); // Ensure we clean up testing on component destroy
    });
</script>
  
<div class="bg-gray-50 p-4">
    <div class="flex gap-8">
        <!-- Always visible LiveFeed section - fixed width -->
        <div class="w-[420px] flex flex-col gap-8 bg-blue-100/50 p-4 rounded-xl">
            <div class="top-5 sticky">
                <LiveFeed />
            </div>
            <ParameterPanel class="flex-1 min-w-[400px]" />
            
            {#if isTestingAll}
                <div class="bg-white/50 p-4 rounded-lg space-y-2">
                    <div class="flex justify-between items-center">
                        <span class="font-medium">Testing Progress</span>
                        <span class="text-sm">{currentStep}/{totalSteps}</span>
                    </div>
                    {#if testingStatus}
                        <p class="text-sm text-gray-600">{testingStatus}</p>
                    {/if}
                    <div class="w-full bg-gray-200 rounded-full h-2">
                        <div 
                            class="bg-blue-500 h-2 rounded-full transition-all duration-300" 
                            style="width: {(currentStep / totalSteps * 100) || 0}%"
                        ></div>
                    </div>
                </div>
            {/if}

            <!-- Add Test All button -->
            <button 
                class="w-full px-4 py-2 rounded-lg font-medium transition-colors {isTestingAll ? 'bg-red-500 text-white' : 'bg-blue-500 text-white'}"
                onclick={handleTestAll}
            >
                {isTestingAll ? 'Stop Testing' : 'Test All Options'}
            </button>
        </div>

        <!-- Right side content -->
        <div class="flex-1 flex flex-col gap-8">
            <!-- Panel selection buttons -->
            <div class="flex gap-4">
                <button 
                    class="px-4 py-2 rounded-lg font-medium transition-colors {activePanel === 'rewards' ? 'bg-amber-500 text-white' : 'bg-gray-200 text-gray-700'}"
                    onclick={() => activePanel = /** @type {'rewards'} */ ('rewards')}
                >
                    Rewards
                </button>
                <button 
                class="px-4 py-2 rounded-lg font-medium transition-colors {activePanel === 'llm' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-700'}"
                onclick={() => activePanel = /** @type {'llm'} */ ('llm')}
            >
                LLM Control
            </button>
            </div>

            <!-- Conditional panel display -->
            {#if activePanel === 'rewards'}
                <div class="flex-1 flex flex-wrap gap-8">
                    <div class="flex-1 max-w-[420px] bg-amber-100/50 p-4 rounded-xl">
                        <RewardPanel />
                    </div>
                    <div class="flex-1 min-w-[400px] bg-green-100/50 p-4 rounded-xl">
                        <ActiveRewardsPanel />
                    </div>
                </div>
            {:else if activePanel === 'llm'}
                <div class="flex-1 bg-purple-100/50 p-4 rounded-xl">
                    
                    <LLM />
                </div>
            {/if}
        </div>
    </div>
</div>
<!-- Add PresetsList at the bottom -->
<div class="w-full">
    <PresetsList />
</div>
<style>
    /* Custom grid layout for auto-fitting columns */
    .grid-auto-fit {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 600px), 1fr));
    }
</style>