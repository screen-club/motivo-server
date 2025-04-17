<script>
  import { createEventDispatcher } from 'svelte';
  
  const dispatch = createEventDispatcher();
  
  // Function to handle clicking on the add button
  function handleAddClick() {
    dispatch('add');
  }
</script>

<div 
  class="w-48 h-36 flex items-center justify-center bg-white border-2 border-dashed border-gray-300 rounded-lg hover:border-purple-500 transition-colors duration-200 cursor-pointer"
  on:click={handleAddClick}
>
  <div class="flex flex-col items-center justify-center text-gray-500 hover:text-purple-600">
    <svg xmlns="http://www.w3.org/2000/svg" class="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
    </svg>
    <span class="mt-2 text-sm font-medium">Create Timeline</span>
  </div>
</div>