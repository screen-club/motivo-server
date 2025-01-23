<script>
  export let isLoading;
</script>

<div class="mt-4 flex items-center justify-between px-4 py-2 bg-white rounded-lg shadow-sm">
  <span class="text-sm text-gray-600">
    Status: {isLoading ? 'Loading...' : 'Live'}
  </span>
  <div class="flex items-center space-x-2">
    <div class={`w-2 h-2 rounded-full ${isLoading ? 'bg-yellow-400' : 'bg-green-500'}`}></div>
    <span class="text-sm text-gray-600">{isLoading ? 'Buffering' : 'Connected'}</span>
  </div>
</div> 