<script>
  import { onMount } from 'svelte';
  import { fly } from 'svelte/transition';

  let videos = $state([]);
  let error = $state(null);
  let loading = $state(true);

  const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:5002';

  onMount(async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      videos = data;
    } catch (e) {
      console.error("Failed to fetch videos:", e);
      error = e.message;
    } finally {
      loading = false;
    }
  });

  function formatBytes(bytes, decimals = 2) {
    if (!+bytes) return '0 Bytes'

    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

    const i = Math.floor(Math.log(bytes) / Math.log(k))

    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
  }

  function formatDate(timestamp) {
    return new Date(timestamp * 1000).toLocaleString();
  }

</script>

<div class="container mx-auto p-4" in:fly={{ y: 20, duration: 300 }}>
  <h2 class="text-2xl font-semibold mb-6 text-gray-800">Rendered Videos</h2>

  {#if loading}
    <div class="text-center py-10">
      <p>Loading videos...</p>
      <!-- Optional: Add a spinner -->
    </div>
  {:else if error}
    <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
      <strong class="font-bold">Error:</strong>
      <span class="block sm:inline"> Failed to load videos. {error}</span>
    </div>
  {:else if videos.length === 0}
    <div class="text-center py-10 text-gray-500">
      <p>No rendered videos found.</p>
    </div>
  {:else}
    <ul class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
      {#each videos as video (video.filename)}
        <li class="bg-white rounded-lg shadow overflow-hidden transition-shadow duration-200 hover:shadow-md">
          <div class="p-4">
            <h3 class="font-semibold text-gray-900 truncate mb-2" title={video.filename}>{video.filename}</h3>
            {#if video.error}
              <p class="text-sm text-red-600">Error: {video.error}</p>
            {:else}
               <video controls preload="metadata" class="w-full aspect-video bg-black rounded mb-2">
                 <source src="{apiBaseUrl}{video.url}" type="video/mp4"> <!-- Assuming MP4, adjust if needed -->
                 Your browser does not support the video tag.
               </video>
               <p class="text-sm text-gray-600">Size: {formatBytes(video.size)}</p>
               <p class="text-sm text-gray-600">Created: {formatDate(video.created_at)}</p>
               <a href="{apiBaseUrl}{video.url}" target="_blank" rel="noopener noreferrer" class="mt-3 inline-block text-sm text-blue-600 hover:text-blue-800">
                 Open Raw Video
               </a>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div> 