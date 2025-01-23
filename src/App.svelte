<script>
  import { onMount, onDestroy } from 'svelte';
  
  let currentImageUrl = `http://localhost:5002/amjpeg?${Date.now()}`;
  let nextImageUrl;
  let refreshInterval;
  let isLoading = true;
  
  function loadNextImage() {
    nextImageUrl = `http://localhost:5002/amjpeg?${Date.now()}`;
  }

  function handleImageLoad() {
    isLoading = false;
    currentImageUrl = nextImageUrl;
    setTimeout(loadNextImage, 100); // Adjust this delay as needed
  }

  function handleImageError() {
    // If image fails to load, try loading the next one
    loadNextImage();
  }
  
  onMount(() => {
    loadNextImage();
  });
  
  onDestroy(() => {
    if (refreshInterval) clearInterval(refreshInterval);
  });
</script>

<main class="min-h-screen flex flex-col items-center justify-center p-8 bg-gradient-to-b from-gray-50 to-gray-100">
 
  <h1 class="text-5xl font-bold mb-16 bg-clip-text text-transparent bg-gradient-to-r from-purple-600 to-orange-600"> Live MJPEG Feed </h1>

 
    <div class="aspect-square max-w-[500px] mx-auto overflow-hidden rounded-xl shadow-md border border-gray-100">
      <img 
        src={currentImageUrl}
        alt="MJPEG Feed"
        class="w-full h-full object-cover"
      />
      <img 
        src={nextImageUrl}
        alt="MJPEG Feed"
        class="hidden"
        on:load={handleImageLoad}
        on:error={handleImageError}
      />
    </div>
 

</main>

