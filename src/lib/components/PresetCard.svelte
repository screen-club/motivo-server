<script>
  import TagInput from "./TagsInput.svelte";
  import UserInput from "./UserInput.svelte";
  import { DbService } from "../../services/db";
  import { fade } from 'svelte/transition';
  import { get } from 'svelte/store';
  import { currentlyPlayingPresetId } from "../../stores/playbackStore";
  import { onDestroy, createEventDispatcher } from 'svelte';
  import { llmPromptStore, defaultPresetPromptStore } from '../../stores/llmInteractionStore';
  
  const dispatch = createEventDispatcher();

  export let preset;
  export let onLoad;
  export let onDelete;
  export let onRegenerateThumbnail;
  export let isDraggable = true;
  export let isRegenerating = false;
  export let allTags = [];
  export let allUsers = [];
  export let initialLoading = false;

  // ... existing code ...

  function handleIAPrompt() {
    stopAnimation();
    const defaultPrompt = get(defaultPresetPromptStore);
    llmPromptStore.set(defaultPrompt);
  }
</script>