/**
 * User store to handle user selection and persistence
 */
import { writable } from 'svelte/store';

// Get the stored user from localStorage or default to 'all'
const storedUser = typeof localStorage !== 'undefined' 
  ? localStorage.getItem('selectedUser') || 'all'
  : 'all';

// Create the writable store with the initial value
export const selectedUser = writable(storedUser);

// Subscribe to changes and update localStorage
selectedUser.subscribe(value => {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('selectedUser', value);
  }
});