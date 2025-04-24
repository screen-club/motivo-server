import { writable } from "svelte/store";

// Store for settings specific to the Control page UI

// Initial value for mix weight
const initialMixWeight = 0.5;

// Writable store for the mix weight slider value
export const mixWeightStore = writable(initialMixWeight);
