<script>
  import { onMount, onDestroy } from 'svelte';
  import { websocketService } from '../services/websocket';
  import { writable } from 'svelte/store';
  import { Link } from "svelte-routing";
  import { location } from "../stores/routeStore";
  import { versionInfo } from '../stores/versionStore';
  import UserSelect from './Header/UserSelect.svelte';

  export let title = "Liminal Motivo Server";
  
  const connectedClients = writable(0);
  const uniqueClients = writable(0);
  let cleanupMessageHandler;

  $: isControlActive = $location === '/control' || $location === '/';
  $: isTestingActive = $location === '/testing';
  $: isVideosActive = $location === '/videos';

  function handleMessage(data) {
    if (data.type === "debug_model_info") {
      $connectedClients = data.connected_clients;
      $uniqueClients = data.unique_clients;
    }
  }

  onMount(() => {
    cleanupMessageHandler = websocketService.addMessageHandler(handleMessage);
  });

  onDestroy(() => {
    if (cleanupMessageHandler) cleanupMessageHandler();
  });
</script>

<header class="w-full bg-white shadow-sm">
  <div class="w-full mx-auto">
    <div class="px-4 sm:px-6 lg:px-8 py-2 flex justify-between items-center">
      <h1 class="text-2xl font-black text-black whitespace-nowrap">
        {title}
      </h1>
      <nav class="flex gap-4 items-center">
        <Link 
          to="/control" 
          class={isControlActive ? 'text-blue-600 font-medium' : 'hover:text-blue-600'}>
          Control
        </Link>
        <Link 
          to="/videos" 
          class={isVideosActive ? 'text-blue-600 font-medium' : 'hover:text-blue-600'}>
          Videos
        </Link>
        <Link 
          to="/testing" 
          class={isTestingActive ? 'text-blue-600 font-medium' : 'hover:text-blue-600'}>
          Testing
        </Link>
        <UserSelect />
      </nav>
    </div>
  </div>
</header> 