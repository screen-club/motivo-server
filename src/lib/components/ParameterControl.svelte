<script>
  import { parameterStore } from '../stores/parameterStore';

  export let name;
  export let label;
  export let type = 'range';
  export let min = 0;
  export let max = 100;
  export let step = 1;
  export let options = undefined;

  // Get the current value from the store using $ syntax
  $: value = $parameterStore[name];

  function handleInput(event) {
    const newValue = type === 'select' ? 
      parseInt(event.target.value) : 
      parseFloat(event.target.value);
    parameterStore.updateParameter(name, newValue);
  }
</script>

<div class="space-y-1">
  <div class="flex justify-between items-center">
    <label class="text-xs font-medium text-gray-700">
      {label}
    </label>
    <span class="text-xs font-medium text-gray-600">
      {value}
    </span>
  </div>
  
  {#if type === 'range'}
    <input 
      {type}
      bind:value={value}
      {min}
      {max}
      {step}
      on:input={handleInput}
      class="w-full h-1 bg-gray-200 rounded-lg appearance-none cursor-pointer"
    />
  {:else if type === 'select'}
    <select 
      bind:value={value}
      on:change={handleInput}
      class="block w-full text-sm rounded border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
    >
      {#each options as option}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
  {/if}
</div> 