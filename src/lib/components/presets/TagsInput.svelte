<!-- TagInput.svelte -->
<script>
    import { createEventDispatcher } from "svelte";

    export let tags = [];
    export let allTags = [];
    export let placeholder = "Add tag...";

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

    $: {
        if (inputValue.trim()) {
            filteredTags = allTags
                .filter(
                    (tag) =>
                        tag.toLowerCase().includes(inputValue.toLowerCase()) &&
                        !tags.includes(tag),
                )
                .slice(0, 5);
            showSuggestions = true;
        } else {
            showSuggestions = false;
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

    <input
        type="text"
        {placeholder}
        bind:value={inputValue}
        on:keydown={handleKeydown}
        on:focus={() => (showSuggestions = !!inputValue)}
        class="w-full px-2 py-1 text-sm border rounded"
    />

    {#if showSuggestions && filteredTags.length > 0}
        <div
            class="absolute z-10 w-full bg-white border rounded-b shadow-lg mt-1"
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
