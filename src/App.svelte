<script>
  import { Router, Link, Route } from "svelte-routing";
  import { onMount, onDestroy } from "svelte";
  import { websocketService } from "./lib/services/websocket";
  import Header from './lib/components/Header.svelte';
  import LiveFeed from './lib/components/LiveFeed';
  import Home from './lib/pages/Home.svelte';
  import About from './lib/pages/About.svelte';
  import Control from './lib/pages/Control.svelte';
  import Videos from './lib/pages/Videos.svelte';
  import Footer from './lib/components/Footer.svelte';
  import VersionInfo from './lib/components/VersionInfo.svelte';
  
  export let url = "";

  // Connect websocketService when app mounts
  onMount(() => {
    // Explicitly connect once at the app level
    websocketService.connect();
  });
</script>

<div class="flex flex-col min-h-screen">
  <Router {url}>
    <Header />
    
    <main class="flex-1 bg-gray-50">
      <div class="h-full">
        <Route path="/"><Control /></Route>
        <Route path="/testing"><Home /></Route>
        <Route path="/about"><About /></Route>
        <Route path="/videos"><Videos /></Route>
        <Route path="/live"><LiveFeed /></Route>
        <Route path="/control"><Control /></Route>
      </div>
    </main>

    <Footer />
   
  </Router>
</div>

