<script>
  import { onMount } from 'svelte';
  import { selectedUser } from '../../stores/userStore';
  import { DbService } from '../../services/db';

  // Store all users for the dropdown
  let allUsers = [];

  // Function to load all users from presets
  async function loadAllUsers() {
    try {
      const presets = await DbService.getAllConfigs();
      const users = Array.from(new Set(
        presets.flatMap(p => p.users || []).filter(Boolean)
      ));
      allUsers = users;
    } catch (error) {
      console.error("Failed to load users:", error);
    }
  }

  onMount(async () => {
    // Load all users on mount
    await loadAllUsers();
  });
</script>

<div class="flex items-center space-x-2">
  <label for="user-select" class="text-blue-500 whitespace-nowrap">
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
      <path stroke-linecap="round" stroke-linejoin="round" d="M17.982 18.725A7.488 7.488 0 0 0 12 15.75a7.488 7.488 0 0 0-5.982 2.975m11.963 0a9 9 0 1 0-11.963 0m11.963 0A8.966 8.966 0 0 1 12 21a8.966 8.966 0 0 1-5.982-2.275M15 9.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
    </svg>
  </label>
  <select 
    id="user-select"
    bind:value={$selectedUser}
    class="border rounded-md px-2 py-1 text-sm min-w-[120px]"
  >
    <option value="all">All Users</option>
    {#each allUsers as user}
      <option value={user}>{user}</option>
    {/each}
    <option value="add_new">+ Add New User</option>
  </select>

  {#if $selectedUser === 'add_new'}
    <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" on:click|self={() => $selectedUser = 'all'}>
      <div class="bg-white p-4 rounded-lg shadow-lg">
        <h3 class="text-lg font-bold mb-2">Add New User</h3>
        <input 
          type="text" 
          id="new-user-input"
          placeholder="Enter username"
          class="border rounded-md px-2 py-1 w-full mb-2"
          on:keydown={e => {
            if (e.key === 'Enter') {
              const newUser = e.target.value?.trim();
              if (newUser) {
                allUsers = [...allUsers, newUser];
                $selectedUser = newUser;
              } else {
                $selectedUser = 'all';
              }
            }
          }}
          autofocus
        />
        <div class="flex justify-end gap-2">
          <button 
            class="px-3 py-1 bg-gray-200 rounded hover:bg-gray-300"
            on:click={() => $selectedUser = 'all'}
          >
            Cancel
          </button>
          <button 
            class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
            on:click={() => {
              const input = document.getElementById('new-user-input');
              const newUser = input?.value?.trim();
              if (newUser) {
                allUsers = [...allUsers, newUser];
                $selectedUser = newUser;
              } else {
                $selectedUser = 'all';
              }
            }}
          >
            Add
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>