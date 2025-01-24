<script>
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();

  export let name;
  export let label;
  export let type = 'range';
  export let min = 0;
  export let max = 100;
  export let step = 1;
  export let options = undefined;
  export let value; // Accept value from parent

  function handleInput(event) {
    let newValue;
    if (type === 'select') {
      newValue = event.target.value === '' ? null : parseInt(event.target.value);
    } else {
      newValue = parseFloat(event.target.value);
    }
    
    if (!isNaN(newValue)) {
      console.log(`ParameterControl ${name} value changed to:`, newValue);
      dispatch('change', newValue);
    }
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
      {value}
      {min}
      {max}
      {step}
      on:input={handleInput}
      class="w-full h-1 bg-gray-200 rounded-lg appearance-none cursor-pointer"
    />
  {:else if type === 'select'}
    <select 
      bind:value
      on:change={handleInput}
      class="block w-full text-sm rounded border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
    >
      {#each options as option}
        <option value={option.value} selected={value === option.value}>
          {option.label}
        </option>
      {/each}
    </select>
  {/if}
</div> 