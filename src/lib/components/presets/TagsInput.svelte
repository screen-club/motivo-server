<!-- TagInput.svelte -->
<script>
    import { createEventDispatcher } from "svelte";

    export let tags = [];
    export let allTags = [];
    export let placeholder = "Add tag...";
    export let isLoading = false;

    let inputValue = "";
    let showSuggestions = false;
    let filteredTags = [];

    const dispatch = createEventDispatcher();

    function handleKeydown(event) {
        if (event.key === "Enter" && inputValue.trim()) {
            addTag(inputValue.trim());
            event.preventDefault();
        }
    }

    function addTag(tag) {
        if (!tags.includes(tag)) {
            const newTags = [...tags, tag];
            dispatch("update", { tags: newTags });
        }
        inputValue = "";
        showSuggestions = false;
    }

    function removeTag(tagToRemove) {
        const newTags = tags.filter((tag) => tag !== tagToRemove);
        dispatch("update", { tags: newTags });
    }

    // Ensure allTags is uniquified
    $: uniqueAllTags = Array.from(new Set(allTags));
    
    // Update filtered tags whenever input value changes or allTags changes
    $: {
        if (inputValue.trim()) {
            // Filter tags that match input text and aren't already selected
            filteredTags = uniqueAllTags
                .filter(
                    (tag) =>
                        tag.toLowerCase().includes(inputValue.toLowerCase()) &&
                        !tags.includes(tag)
                );
        } else {
            // Show all available tags that aren't already selected
            filteredTags = uniqueAllTags.filter(tag => !tags.includes(tag));
        }
    }
</script>

<div class="relative">
    <div class="flex flex-wrap gap-2 mb-2">
        {#each tags as tag}
            <span
                class="bg-purple-100 text-purple-800 text-xs px-2 py-1 rounded-full flex items-center"
            >
                {tag}
                <button
                    class="ml-1 text-purple-600 hover:text-purple-800 flex items-center justify-center w-4 h-4"
                    on:click={() => removeTag(tag)}
                    title="Remove tag"
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        class="w-3 h-3"
                    >
                        <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                    </svg>
                </button>
            </span>
        {/each}
    </div>

    <div class="relative">
        <input
            type="text"
            {placeholder}
            bind:value={inputValue}
            on:keydown={handleKeydown}
            on:focus={() => (showSuggestions = true)}
            on:input={() => (showSuggestions = true)}
            on:blur={() => setTimeout(() => (showSuggestions = false), 300)}
            class="w-full px-2 py-1 text-sm border rounded {isLoading ? 'pr-8' : ''}"
            disabled={isLoading}
        />
        {#if isLoading}
            <div class="absolute right-2 top-1/2 -translate-y-1/2">
                <svg class="animate-spin h-4 w-4 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
            </div>
        {/if}
    </div>

    {#if showSuggestions && filteredTags.length > 0}
        <div
            class="absolute z-10 w-full bg-white border rounded-b shadow-lg mt-1 max-h-32 overflow-y-auto"
        >
            {#each filteredTags as suggestion}
                <button
                    class="w-full text-left px-3 py-1 hover:bg-gray-100 text-sm"
                    on:click={() => addTag(suggestion)}
                >
                    {suggestion}
                </button>
            {/each}
        </div>
    {/if}
</div>
