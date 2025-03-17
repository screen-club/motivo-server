<!-- UserInput.svelte -->
<script>
    import { createEventDispatcher } from "svelte";

    export let users = [];
    export let allUsers = [];
    export let placeholder = "Add user...";

    let inputValue = "";
    let showSuggestions = false;
    let filteredUsers = [];

    const dispatch = createEventDispatcher();

    function handleKeydown(event) {
        if (event.key === "Enter" && inputValue.trim()) {
            addUser(inputValue.trim());
            event.preventDefault();
        }
    }

    function addUser(user) {
        if (!users.includes(user)) {
            const newUsers = [...users, user];
            dispatch("update", { users: newUsers });
        }
        inputValue = "";
        showSuggestions = false;
    }

    function removeUser(userToRemove) {
        const newUsers = users.filter((user) => user !== userToRemove);
        dispatch("update", { users: newUsers });
    }

    // Ensure allUsers is uniquified
    $: uniqueAllUsers = Array.from(new Set(allUsers));
    
    // Update filtered users whenever input value changes or allUsers changes
    $: {
        if (inputValue.trim()) {
            // Filter users that match input text and aren't already selected
            filteredUsers = uniqueAllUsers
                .filter(
                    (user) =>
                        user.toLowerCase().includes(inputValue.toLowerCase()) &&
                        !users.includes(user)
                );
        } else {
            // Show all available users that aren't already selected
            filteredUsers = uniqueAllUsers.filter(user => !users.includes(user));
        }
    }
</script>

<div class="relative">
    <div class="flex flex-wrap gap-2 mb-2">
        {#each users as user}
            <span
                class="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full flex items-center"
            >
                {user}
                <button
                    class="ml-1 text-blue-600 hover:text-blue-800 flex items-center justify-center w-4 h-4"
                    on:click={() => removeUser(user)}
                    title="Remove user"
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
        on:focus={() => (showSuggestions = true)}
        on:input={() => (showSuggestions = true)}
        on:blur={() => setTimeout(() => (showSuggestions = false), 300)}
        class="w-full px-2 py-1 text-sm border rounded"
    />

    {#if showSuggestions && filteredUsers.length > 0}
        <div
            class="absolute z-10 w-full bg-white border rounded-b shadow-lg mt-1 max-h-32 overflow-y-auto"
        >
            {#each filteredUsers as suggestion}
                <button
                    class="w-full text-left px-3 py-1 hover:bg-gray-100 text-sm"
                    on:click={() => addUser(suggestion)}
                >
                    {suggestion}
                </button>
            {/each}
        </div>
    {/if}
</div>