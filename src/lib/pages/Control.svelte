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
    import { defaultPresetPromptStore } from '../stores/llmInteractionStore';
    
    let isSocketReady = $state(false);
    let cleanupListener;
    let videoIntersectionTriggerRef; // Ref for the placeholder element
    let videoWrapperRef;   // Ref for the actual video wrapper
    let isPiPMode = $state(false);
    let observer;
    let isLargePiP = $state(false); // State for large PiP mode
    let videoContainerRef; // Ref for the outer container
    
    // Get valid panel from localStorage or default to 'rewards'
    const storedPanel = localStorage.getItem('controlActivePanel');
    /** @type {'rewards' | 'llm'} */
    let activePanel = $state(
      storedPanel === 'rewards' || storedPanel === 'llm' ? storedPanel : 'rewards'
    );
    
    // State for default preset prompt
    let isEditingDefaultPrompt = $state(false);
    let defaultPromptValue = $state('');
    
    // Subscribe to defaultPresetPromptStore
    $effect(() => {
        defaultPromptValue = $defaultPresetPromptStore;
    });
    
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

    // Function to save updated default prompt
    function saveDefaultPrompt() {
        if (defaultPromptValue.trim()) {
            defaultPresetPromptStore.set(defaultPromptValue);
            isEditingDefaultPrompt = false;
        }
    }

    onMount(() => {
        cleanupListener = websocketService.onReadyStateChange((ready) => {
            isSocketReady = ready;
        });
        
        isSocketReady = websocketService.getSocket()?.readyState === WebSocket.OPEN;

        // --- Intersection Observer for PiP trigger ---
        const options = { root: null, rootMargin: '0px', threshold: 0 }; 
        observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                isPiPMode = !entry.isIntersecting;
                if (entry.isIntersecting) {
                    isLargePiP = false;
                }
            });
        }, options);

        if (videoIntersectionTriggerRef) { // Use the new trigger ref
            observer.observe(videoIntersectionTriggerRef);
        }

        // Cleanup observers on destroy
        onDestroy(() => {
            if (observer && videoIntersectionTriggerRef) { // Use the new trigger ref
                observer.unobserve(videoIntersectionTriggerRef);
            }
            if (cleanupListener) cleanupListener();
            rewardStore.stopTesting();
        });
    });

    // Add/remove class to outer container based on PiP state
    $effect(() => {
        const pipActive = isPiPMode || isLargePiP;
        if (videoContainerRef) {
            videoContainerRef.classList.toggle('has-pip-active', pipActive);
        }
    });

    // Button handler only toggles the large state
    function handleTogglePip() {
        isLargePiP = !isLargePiP;
    }
</script>
  
<div class="bg-gray-50 p-4">
    <div class="flex gap-8">
        <!-- Left column -->
        <div class="w-[420px] flex flex-col gap-8">
            <!-- Outer container that stays in flow -->
            <div class="video-container relative" bind:this={videoContainerRef}> 
                <!-- Element for Intersection Observer trigger -->
                <div bind:this={videoIntersectionTriggerRef} class="absolute top-0 h-1 w-full"></div>

                <!-- Inner Wrapper for the Video Feed (this is what moves/resizes) -->
                <div 
                  class:pip-mode={isPiPMode || isLargePiP} 
                  class:pip-large={isLargePiP}
                  class="video-wrapper"
                >
                    <LiveFeed {isPiPMode} {isLargePiP} on:togglePip={handleTogglePip} />
                    
                    <!-- Scaled Parameter Panel for PiP -->
                    <ParameterPanel 
                      class="pip-params {!(isPiPMode || isLargePiP) ? 'hidden' : ''}"
                      isCompact={true}
                    />
                </div>
            </div>

            <!-- Original Parameter Panel (Hidden during PiP) -->
            <ParameterPanel class="original-params flex-1 min-w-[400px] {(isPiPMode || isLargePiP) ? 'invisible' : ''}" />
            
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
                    <!-- Default Preset Prompt Editor -->
                    <div class="mb-4 p-3 bg-white rounded-lg shadow-sm">
                        <div class="flex justify-between items-center mb-2">
                            <h3 class="font-medium text-gray-800">Default Preset Prompt</h3>
                            {#if isEditingDefaultPrompt}
                                <div class="flex gap-2">
                                    <button 
                                        class="px-3 py-1 text-xs bg-green-500 text-white rounded-md hover:bg-green-600"
                                        onclick={saveDefaultPrompt}
                                    >
                                        Save
                                    </button>
                                    <button 
                                        class="px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
                                        onclick={() => {
                                            defaultPromptValue = $defaultPresetPromptStore;
                                            isEditingDefaultPrompt = false;
                                        }}
                                    >
                                        Cancel
                                    </button>
                                </div>
                            {:else}
                                <button 
                                    class="px-3 py-1 text-xs bg-blue-500 text-white rounded-md hover:bg-blue-600"
                                    onclick={() => isEditingDefaultPrompt = true}
                                >
                                    Edit
                                </button>
                            {/if}
                        </div>
                        
                        {#if isEditingDefaultPrompt}
                            <textarea
                                bind:value={defaultPromptValue}
                                class="w-full p-2 border border-gray-300 rounded-md h-24 text-sm"
                                placeholder="Enter default prompt for preset analysis..."
                            ></textarea>
                            <p class="text-xs text-gray-500 mt-1">This prompt will be used when analyzing presets with the IA button.</p>
                        {:else}
                            <p class="text-sm bg-gray-50 p-2 rounded-md">{defaultPromptValue}</p>
                        {/if}
                    </div>
                    
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
    .video-container {
        position: relative; /* Needed for the ::before pseudo-element */
    }

    /* Add padding to the container when inner video is PiP */
    .video-container.has-pip-active {
        padding-top: 240px; /* Approximate height of the video feed */
        /* Adjust height if necessary */
    }

    .video-wrapper {
        transition: all 0.3s ease-in-out;
        position: relative; /* Needed for absolute positioning of pip-params */
        overflow: hidden; /* Hide scaled content overflow */
    }

    .video-wrapper.pip-mode {
        position: fixed;
        top: 1rem;
        left: 1rem;
        width: 420px; /* Default PiP width (matches original container) */
        height: auto;
        z-index: 50;
        border-radius: 0.5rem;
        overflow: hidden; /* Ensure overflow hidden */
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        transition: all 0.3s ease-in-out;
    }

    .video-wrapper.pip-large {
        width: 800px; /* Override for large PiP with fixed width */
        overflow: hidden; /* Ensure overflow hidden */
        /* Other styles are inherited from pip-mode */
    }

    .pip-params {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        transform: scale(0.35); /* Adjust scale factor as needed */
        transform-origin: bottom left;
        background: rgba(255, 255, 255, 0.9);
        padding: 0.5rem; /* Add some padding */
        border-top: 1px solid rgba(0,0,0,0.1);
        pointer-events: none; /* Disable interaction */
        transition: opacity 0.3s ease-in-out;
        opacity: 1;
    }

    /* Custom grid layout for auto-fitting columns */
    .grid-auto-fit {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 600px), 1fr));
    }
</style>