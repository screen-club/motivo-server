<script>
  let { title = undefined, columns = 1, isCompact = false } = $props();
</script>

<div class="" class:mb-4={!isCompact} class:mb-1={isCompact}>
  {#if title}
    <h3 
      class="text-sm font-medium text-gray-700" 
      class:mb-2={!isCompact} 
      class:hidden={isCompact}
    >{title}</h3>
  {/if}
  <div 
    class="grid grid-cols-{columns}" 
    class:gap-x-6={!isCompact} class:gap-y-3={!isCompact} 
    class:gap-x-1={isCompact} class:gap-y-0={isCompact}
  >
    <slot />
  </div>
</div>