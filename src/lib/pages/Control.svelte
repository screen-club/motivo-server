<script>
    import { onMount, onDestroy } from 'svelte';
    import LiveFeed from '../components/LiveFeed.svelte';
    import ParameterPanel from '../components/ParameterPanel.svelte';
    import RewardPanel from '../components/RewardPanel.svelte';
    import { parameterStore } from '../stores/parameterStore';
    import { rewardStore } from '../stores/rewardStore';
  
    let socket;
  
    onMount(() => {
    
        console.log("hello")
      socket = new WebSocket('ws://localhost:8765');
      
      socket.onopen = () => {
        console.log('WebSocket connected');
      };
  
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // Route messages to appropriate stores based on type
        if (data.type === "parameters" || data.type === "parameters_updated") {
          parameterStore.set(data.parameters);
        }
        // Add other message type handling as needed
      };
  
      socket.onclose = () => {
        console.log('WebSocket disconnected');
      };
  
      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
  
      // Set the socket in both stores once connected
      parameterStore.setSocket(socket);
      rewardStore.setSocket(socket);
    });
  
    onDestroy(() => {
      if (socket) {
        parameterStore.disconnect();
        rewardStore.disconnect();
        socket.close();
      }
    });
  </script>
  
  <div class="flex gap-4">
    <div class="flex flex-col gap-4">
      <ParameterPanel />
      <RewardPanel />
    </div>
    <div class="flex-grow">
      <LiveFeed />
    </div>
  </div>