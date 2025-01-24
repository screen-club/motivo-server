<script>
  import { Router, Link, Route } from "svelte-routing";
  import Header from './lib/components/Header.svelte';
  import LiveFeed from './lib/components/LiveFeed.svelte';
  // Add new page components
  import Home from './lib/pages/Home.svelte';
  import About from './lib/pages/About.svelte';
  import Control from './lib/pages/Control.svelte';
  
  // Required for routing to work
  export let url = "";
</script>

<div>
  <Router {url}>
    <main class="min-h-screen flex flex-col bg-gray-50">
      <Header />
      
      <div class="container mx-auto px-4 flex-grow">
        <Route path="/" component={Home} />
        <Route path="/about" component={About} />
        <Route path="/live" component={LiveFeed} />
        <Route path="/control" component={Control} />
      </div>

      <footer class="w-full py-4 bg-white shadow-md mt-auto">
        <nav class="container mx-auto px-4 flex gap-4 justify-center">
          <Link to="/" class="hover:text-blue-600">Home</Link>
          <Link to="/live" class="hover:text-blue-600">Live Feed</Link>
          <Link to="/control" class="hover:text-blue-600">Control</Link>
          <Link to="/about" class="hover:text-blue-600">About</Link>
        </nav>
      </footer>
    </main>
  </Router>
</div>

