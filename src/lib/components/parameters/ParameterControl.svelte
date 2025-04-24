<script>
  import { createEventDispatcher } from 'svelte';
  import { REWARD_TYPES } from '../../stores/rewardStore';
  
  let dispatch = createEventDispatcher();

  let {
    name,
    label,
    type = 'range',
    min = 0,
    max = 100,
    step = 1,
    options = undefined,
    value,
    defaultValue = undefined,
    isCompact = false
  } = $props();

  // Auto-configure from REWARD_TYPES if applicable
  $effect(() => {
    if (name && REWARD_TYPES[name]) {
      const paramConfig = REWARD_TYPES[name][label];
      if (paramConfig) {
        type = paramConfig.type;
        if (type === 'range') {
          min = paramConfig.min;
          max = paramConfig.max;
          step = paramConfig.step;
        } else if (type === 'select') {
          options = paramConfig.options.map(opt => ({ value: opt, label: opt }));
        }
        if (defaultValue === undefined) {
          defaultValue = paramConfig.default;
        }
      }
    }
  });

  // Initialize value with default if not set
  $effect(() => {
    if (value === undefined && defaultValue !== undefined) {
      value = defaultValue;
    }
  });

  function handleInput(event) {
    let newValue;
    if (type === 'select') {
      newValue = event.target.value === '' ? null : event.target.value;
    } else if (type === 'range') {
      newValue = parseFloat(event.target.value);
      value = newValue;
    } else if (type === 'checkbox') {
      newValue = event.target.checked;
      value = newValue;
    }
    
    if (newValue !== undefined) {
      dispatch('change', {
        name,
        value: newValue
      });
    }
  }
</script>

<div class="" class:mb-4={!isCompact} class:mb-0.5={isCompact}>
  <div class="flex justify-between items-center" class:mb-1.5={!isCompact} class:mb-0.5={isCompact}>
    <label 
      for={`param-${name}`} 
      class="font-medium uppercase tracking-wide" 
      class:text-xs={!isCompact} class:text-gray-500={!isCompact}
      class:text-[9px]={isCompact} class:text-gray-400={isCompact}
    >
      {label}
    </label>
    {#if type !== 'checkbox'}
      <span 
        class="font-medium tabular-nums" 
        class:text-xs={!isCompact} class:text-gray-900={!isCompact}
        class:text-[9px]={isCompact} class:text-gray-700={isCompact}
      >
        {value?.toFixed?.(2) ?? value}
      </span>
    {/if}
  </div>
  
  <div class="w-full">
    {#if type === 'range'}
      <input 
        id={`param-${name}`}
        type="range"
        {value}
        {min}
        {max}
        {step}
        on:input={handleInput}
        class="w-full rounded-lg appearance-none cursor-pointer accent-blue-600 range-control" 
        class:h-1.5={!isCompact} class:bg-gray-200={!isCompact} 
        class:h-1={isCompact} class:bg-gray-100={isCompact}
        class:range-compact={isCompact}
      />
    {:else if type === 'select'}
      <select 
        id={`param-${name}`}
        {value}
        on:change={handleInput}
        class="block w-full rounded-md border-0 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-blue-600 bg-white shadow-sm appearance-none bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%236b7280%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22m6%208%204%204%204-4%22%2F%3E%3C%2Fsvg%3E')] bg-[position:right_0.5rem_center] bg-[length:1em_1em] bg-no-repeat"
        class:text-xs={!isCompact} class:py-1.5={!isCompact} class:pl-2={!isCompact} class:pr-8={!isCompact}
        class:text-[9px]={isCompact} class:py-0={isCompact} class:pl-1={isCompact} class:pr-4={isCompact}
      >
        {#each options as option}
          <option value={option.value} selected={value === option.value}>
            {option.label}
          </option>
        {/each}
      </select>
    {:else if type === 'checkbox'}
      <label for={`param-${name}`} class="relative inline-flex items-center cursor-pointer">
        <input
          id={`param-${name}`}
          type="checkbox"
          checked={value}
          on:change={handleInput}
          class="sr-only peer"
        />
        <div class="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
      </label>
    {/if}
  </div>
</div>

<style>
  .range-control.range-compact::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      height: 0.375rem; /* Equivalent to h-1.5 */
      width: 0.375rem;  /* Equivalent to w-1.5 */
      background-color: #2563eb; /* Explicitly blue-600 */
      border-radius: 50%;
      cursor: pointer; /* Keep the pointer */
  }
  .range-control.range-compact::-moz-range-thumb {
      appearance: none;
      height: 0.375rem; /* Equivalent to h-1.5 */
      width: 0.375rem;  /* Equivalent to w-1.5 */
      background-color: #2563eb; /* Explicitly blue-600 */
      border-radius: 50%;
      border: none; /* Remove Firefox default border */
      cursor: pointer; /* Keep the pointer */
  }
</style>