<script>
  export let title = '';
  export let layout = 'grid'; // 'grid' or 'stack'
  export let columns = 2;
</script>

<div class="bg-gray-50 p-2 rounded-lg space-y-2">
  {#if title}
    <h2 class="text-xs font-semibold text-gray-700">{title}</h2>
  {/if}
  
  <div class={layout === 'grid' ? 
    `grid grid-cols-${columns} gap-2` : 
    'space-y-2'
  }>
    <slot />
  </div>
</div> 