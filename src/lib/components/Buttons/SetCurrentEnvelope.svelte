<script>    
  import { currentParamName } from '../../stores/parameterStore';
  // Accept the parameter name as a prop
  export let paramName;
  

</script>

<button 
  class=" w-10 h-10 rounded-full hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-300 transition-colors"
  on:click={$currentParamName = paramName}
  title="Edit {paramName} envelope"
  aria-label="Edit {paramName} envelope"
>
📈
</button>
