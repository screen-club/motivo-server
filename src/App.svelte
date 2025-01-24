<script>
  import { Router, Link, Route } from "svelte-routing";
  import Header from './lib/components/Header.svelte';
  import LiveFeed from './lib/components/LiveFeed.svelte';
  import Home from './lib/pages/Home.svelte';
  import About from './lib/pages/About.svelte';
  import Control from './lib/pages/Control.svelte';
  
  export let url = "";
</script>

<div>
  <Router {url}>
    <main class="min-h-screen flex flex-col bg-gray-50">
      <Header />
      
      <div class="w-full px-4 flex-grow">
        <Route path="/" component={Home} />
        <Route path="/about" component={About} />
        <Route path="/live" component={LiveFeed} />
        <Route path="/control" component={Control} />
      </div>

      <footer class="w-full py-4 bg-white shadow-md mt-auto">
        <nav class="w-full px-4 flex gap-4 justify-center">
          <Link to="/" class="hover:text-blue-600">Home</Link>
          <Link to="/live" class="hover:text-blue-600">Live Feed</Link>
          <Link to="/control" class="hover:text-blue-600">Control</Link>
        </nav>
      </footer>
    </main>
  </Router>
</div>

