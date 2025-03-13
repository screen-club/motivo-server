<script>
  export let title = undefined;
  export let columns = 1;
</script>

<div class="mb-4">
  {#if title}
    <h3 class="text-sm font-medium text-gray-700 mb-2">{title}</h3>
  {/if}
  <div class="grid grid-cols-{columns} gap-x-6 gap-y-3">
    <slot />
  </div>
</div>