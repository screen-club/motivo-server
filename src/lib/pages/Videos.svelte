<script>
  import { onMount } from 'svelte';
  import { fly } from 'svelte/transition';

  let videos = $state([]);
  let error = $state(null);
  let loading = $state(true);

  const apiBaseUrl = import.meta.env.VITE_API_URL

  onMount(async () => {
    console.log("Videos page mounted, fetching from:", `${apiBaseUrl}/api/videos`);
    
    try {
      // Add timestamp to bypass cache and force fresh request
      const timestamp = Date.now();
      const response = await fetch(`${apiBaseUrl}/api/videos?_=${timestamp}`, {
        headers: {
          "Accept": "application/json",
          "Cache-Control": "no-cache"
        }
      });
      
      console.log("Response status:", response.status);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      // Log the raw response text for debugging
      const responseText = await response.text();
      console.log("Raw response:", responseText);
      
      try {
        // Try to parse the JSON
        const rawData = JSON.parse(responseText);
        console.log("Raw videos data fetched:", rawData);
        
        if (Array.isArray(rawData)) {
          // Filter out duplicates based on filename
          const uniqueVideos = [];
          const seenFilenames = new Set();
          for (const video of rawData) {
            if (!seenFilenames.has(video.filename)) {
              uniqueVideos.push(video);
              seenFilenames.add(video.filename);
            } else {
              console.warn(`Duplicate filename found and skipped: ${video.filename}`);
            }
          }
          
          videos = uniqueVideos;
          console.log(`Loaded ${uniqueVideos.length} unique videos (out of ${rawData.length} raw entries)`);
        } else {
          console.error("Response is not an array:", rawData);
          videos = [];
          error = "Invalid response format";
        }
      } catch (parseError) {
        console.error("JSON parse error:", parseError);
        error = "Failed to parse response";
      }
    } catch (e) {
      console.error("Failed to fetch videos:", e);
      error = e.message;
      videos = []; // Set empty array to make sure loading state updates
      
      // Try the fallback test endpoint
     
    } finally {
      loading = false;
      console.log("Loading completed. Videos:", videos.length, "Error:", error);
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
  <div class="flex justify-between items-center mb-6">
    <h2 class="text-2xl font-semibold text-gray-800">Video Recordings</h2>
    <button 
      on:click={() => {
        loading = true;
        // Add timestamp to bypass cache and force fresh request for refresh button too
        const timestamp = Date.now();
        fetch(`${apiBaseUrl}/api/videos?_=${timestamp}`)
          .then(response => {
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response.json();
          })
          .then(data => {
            // Deduplicate on refresh as well
            if (Array.isArray(data)) {
              const uniqueVideos = [];
              const seenFilenames = new Set();
              for (const video of data) {
                if (!seenFilenames.has(video.filename)) {
                  uniqueVideos.push(video);
                  seenFilenames.add(video.filename);
                } else {
                  // console.warn(`Duplicate filename found and skipped during refresh: ${video.filename}`);
                }
              }
              videos = uniqueVideos;
            } else {
              videos = []; // Or handle as error
              console.error("Refreshed data is not an array:", data);
            }
            error = null;
          })
          .catch(e => {
            console.error("Failed to refresh videos:", e);
            error = e.message;
          })
          .finally(() => {
            loading = false;
          });
      }}
      class="px-3 py-1 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-md flex items-center text-sm"
      disabled={loading}
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1 {loading ? 'animate-spin' : ''}" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" />
      </svg>
      {loading ? 'Refreshing...' : 'Refresh'}
    </button>
  </div>

  {#if loading}
    <div class="text-center py-10">
      <p>Loading videos...</p>
    </div>
  {:else if error}
    <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
      <strong class="font-bold">Error:</strong>
      <span class="block sm:inline"> Failed to load videos. {error}</span>
    </div>
  {:else if !loading && videos.length === 0}
    <div class="text-center py-10">
      <div class="max-w-md mx-auto bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <h3 class="text-lg font-medium mb-2">No Recordings Found</h3>
        <p class="text-gray-600 mb-4">
          You can create recording packages (video & SMPL data) from the Motivo simulation using the Record button in the video player.
        </p>
        <div class="bg-gray-50 p-3 rounded text-left">
          <p class="text-sm text-gray-700 mb-2"><span class="font-medium">How to record:</span></p>
          <ol class="text-sm text-gray-600 list-decimal list-inside space-y-1">
            <li>Go to the Control page</li>
            <li>Click the <span class="px-2 py-0.5 bg-green-500 text-white text-xs rounded">Record</span> button in the video player</li>
            <li>The recording will automatically save after 60 seconds, or you can click <span class="px-2 py-0.5 bg-red-500 text-white text-xs rounded">Stop</span> at any time</li>
            <li>Recorded packages will appear here for download. MP4s can be streamed directly.</li>
          </ol>
        </div>
      </div>
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
                 <!-- Use URL directly since it's already in /motivo-videos format -->
                 <source src="{apiBaseUrl + video.url}" type="video/mp4">
                 Your browser does not support the video tag.
               </video>
               <!-- Debug URL info -->
               <div class="text-xs text-gray-400 mb-1">
                 Source: {video.source || 'unknown'}
               </div>
               <!-- Debug info for URL -->
               <div class="text-xs text-gray-400 hidden">Video URL: {apiBaseUrl + video.url}</div>
               <div class="flex gap-2 items-center mb-1">
                 <span class="inline-block px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-800">
                   {video.source || 'video'}
                 </span>
                 <span class="text-xs text-gray-500">{formatBytes(video.size)}</span>
               </div>
               {#if video.package_filename && video.package_url}
               <div class="flex gap-2 items-center mb-1">
                 <span class="inline-block px-2 py-0.5 text-xs rounded-full bg-purple-100 text-purple-800">
                   Data Package
                 </span>
                 {#if video.package_size}
                  <span class="text-xs text-gray-500">{formatBytes(video.package_size)}</span>
                 {/if}
               </div>
               {/if}
               <p class="text-sm text-gray-600 mb-2">Created: {formatDate(video.created_at)}</p>
               <div class="flex flex-wrap gap-2">
                 <a href="{apiBaseUrl + video.url}" 
                    download="{video.filename}" 
                    class="mt-1 inline-flex items-center text-sm text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-3 py-1 rounded-full">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 inline-block mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download Video
                 </a>
                 {#if video.package_filename && video.package_url}
                    <a href="{apiBaseUrl + video.package_url}"
                       download="{video.package_filename}"
                       class="mt-1 inline-flex items-center text-sm font-medium text-purple-700 hover:text-purple-900 bg-purple-100 hover:bg-purple-200 px-3 py-1.5 rounded-lg w-full justify-center">
                       <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 inline-block mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                         <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                       </svg>
                       Download Recording Package (.zip)
                    </a>
                 {:else}
                    <p class="text-xs text-gray-500 mt-1 w-full text-center">Full data package not available for this video.</p>
                 {/if}
                 
                 <!-- Debug button to open video in new tab for testing (removed for cleaner UI by default) -->
                 <!--
                 <a href="{apiBaseUrl + video.url}" 
                    target="_blank"
                    class="mt-1 inline-block text-sm text-gray-600 hover:text-gray-800 bg-gray-50 hover:bg-gray-100 px-3 py-1 rounded-full">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 inline-block mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                    Open Video
                 </a>
                 -->
               </div>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div> 