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
  
  // Function to delete a user from all presets
  async function deleteUser(userToDelete) {
    try {
      // First get all presets
      const presets = await DbService.getAllConfigs();
      
      // Filter presets that contain this user
      const presetsWithUser = presets.filter(p => 
        p.users && p.users.includes(userToDelete)
      );
      
      // For each matching preset, update it to remove the user
      for (const preset of presetsWithUser) {
        const updatedUsers = preset.users.filter(u => u !== userToDelete);
        await DbService.updatePresetUsers(preset.id, updatedUsers);
      }
      
      // Reset selected user if it's the one being deleted
      if ($selectedUser === userToDelete) {
        $selectedUser = 'all';
      }
      
      // Reload users
      await loadAllUsers();
      
    } catch (error) {
      console.error("Failed to delete user:", error);
      alert("Error deleting user: " + error.message);
    }
  }
  
  // For the delete confirmation modal
  let userToDelete = null;
  
  // For the custom dropdown
  let isDropdownOpen = false;
  
  // Click outside directive to close the dropdown
  function clickOutside(node) {
    const handleClick = (event) => {
      if (!node.contains(event.target)) {
        node.dispatchEvent(new CustomEvent('outclick'));
      }
    };
    
    document.addEventListener('click', handleClick, true);
    
    return {
      destroy() {
        document.removeEventListener('click', handleClick, true);
      }
    };
  }

  onMount(async () => {
    // Load all users on mount
    await loadAllUsers();
  });
</script>

<div class="flex items-center space-x-2">
  <div class="text-blue-500 whitespace-nowrap">
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
      <path stroke-linecap="round" stroke-linejoin="round" d="M17.982 18.725A7.488 7.488 0 0 0 12 15.75a7.488 7.488 0 0 0-5.982 2.975m11.963 0a9 9 0 1 0-11.963 0m11.963 0A8.966 8.966 0 0 1 12 21a8.966 8.966 0 0 1-5.982-2.275M15 9.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
    </svg>
  </div>
  
  <div class="relative">
    <!-- Custom dropdown trigger button -->
    <button 
      type="button" 
      on:click={() => isDropdownOpen = !isDropdownOpen}
      class="flex items-center justify-between border rounded-md px-2 py-1 text-sm min-w-[120px] bg-white"
    >
      <span>
        {$selectedUser === 'all' ? 'All Users' : $selectedUser}
      </span>
      <svg 
        class="w-4 h-4 ml-1" 
        xmlns="http://www.w3.org/2000/svg" 
        viewBox="0 0 20 20" 
        fill="currentColor"
      >
        <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
      </svg>
    </button>
    
    <!-- Custom dropdown menu -->
    {#if isDropdownOpen}
      <div 
        class="absolute z-10 mt-1 w-full bg-white rounded-md shadow-lg max-h-60 overflow-auto"
        use:clickOutside
        on:outclick={() => isDropdownOpen = false}
      >
        <!-- All Users option -->
        <button
          class="w-full px-2 py-1 text-left text-sm hover:bg-gray-100"
          class:font-medium={$selectedUser === 'all'}
          on:click={() => {
            $selectedUser = 'all';
            isDropdownOpen = false;
          }}
        >
          All Users
        </button>
        
        <!-- User options with delete icons -->
        {#each allUsers as user}
          <div class="flex items-center px-2 py-1 hover:bg-gray-100 group">
            <button
              class="flex-grow text-left text-sm"
              class:font-medium={$selectedUser === user}
              on:click={() => {
                $selectedUser = user;
                isDropdownOpen = false;
              }}
            >
              {user}
            </button>
            <button 
              class="text-red-500 hover:text-red-700 transition-colors opacity-0 group-hover:opacity-100"
              title="Delete user from all presets"
              on:click|stopPropagation={() => {
                userToDelete = user;
                isDropdownOpen = false;
              }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        {/each}
        
        <!-- No 'Add New User' option anymore -->
      </div>
    {/if}
  </div>

  <!-- Removed Add New User modal -->

  <!-- Delete User Confirmation Modal -->
  {#if userToDelete}
    <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" on:click|self={() => userToDelete = null}>
      <div class="bg-white p-4 rounded-lg shadow-lg max-w-md">
        <div class="flex items-center mb-2 text-red-600">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <h3 class="text-lg font-bold">Delete User</h3>
        </div>
        
        <p class="text-sm mb-4">
          Are you sure you want to delete <span class="font-semibold">{userToDelete}</span>? 
          This will remove this user from all presets. This action cannot be undone.
        </p>
        
        <div class="flex justify-end gap-2">
          <button 
            class="px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 text-sm"
            on:click={() => userToDelete = null}
          >
            Cancel
          </button>
          <button 
            class="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-sm"
            on:click={async () => {
              const userToDeleteCopy = userToDelete;
              userToDelete = null; // Close modal immediately
              await deleteUser(userToDeleteCopy);
            }}
          >
            Delete User
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>