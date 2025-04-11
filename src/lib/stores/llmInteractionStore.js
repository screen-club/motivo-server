import { writable } from "svelte/store";

// Store to hold a prompt intended for the LLM component
// Set to a string value to trigger the LLM, set back to null after processing.
export const llmPromptStore = writable(null);

// Default prompt used when sending presets to LLM
// Persists in localStorage
const storedDefaultPresetPrompt =
  localStorage.getItem("defaultPresetPrompt") ||
  `Make an alternative position of the humanoid. Be creative. It's ok to vary the gravity.`;

export const defaultPresetPromptStore = writable(storedDefaultPresetPrompt);

// Update localStorage when the default prompt changes
defaultPresetPromptStore.subscribe((value) => {
  if (value) {
    localStorage.setItem("defaultPresetPrompt", value);
  }
});
