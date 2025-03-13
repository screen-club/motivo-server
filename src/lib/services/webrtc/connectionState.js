/**
 * WebRTC connection state management
 */
import { writable } from "svelte/store";

// Create stores for tracking WebRTC state
export const isLoading = writable(true);
export const hasStream = writable(false);
export const connectionLogs = writable([]);
export const currentQuality = writable("medium");

/**
 * Connection logging utility
 */
export class ConnectionLogger {
  constructor(maxEntries = 100) {
    this.maxEntries = maxEntries;
    this._logs = [];
  }

  /**
   * Add a log entry with timestamp
   * @param {string} message - Log message
   * @param {string} level - Log level (info, warning, error)
   */
  log(message, level = "info") {
    const timestamp = new Date().toLocaleTimeString();
    const entry = { timestamp, message, level };
    
    // Add to beginning of array (newest first)
    this._logs = [
      entry,
      ...this._logs.slice(0, this.maxEntries - 1),
    ];
    
    // Update the store
    connectionLogs.set(this._logs);
    
    // Also log to console with appropriate level
    switch(level) {
      case "error":
        console.error(`[WebRTC ${timestamp}] ${message}`);
        break;
      case "warning":
        console.warn(`[WebRTC ${timestamp}] ${message}`);
        break;
      default:
        console.log(`[WebRTC ${timestamp}] ${message}`);
    }
    
    return entry;
  }
  
  /**
   * Log an error message
   * @param {string} message - Error message
   * @param {Error} [error] - Optional error object
   */
  error(message, error) {
    let fullMessage = message;
    if (error) {
      fullMessage += `: ${error.message}`;
    }
    return this.log(fullMessage, "error");
  }
  
  /**
   * Log a warning message
   * @param {string} message - Warning message
   */
  warn(message) {
    return this.log(message, "warning");
  }
  
  /**
   * Get all logs
   * @returns {Array} Log entries
   */
  getLogs() {
    return [...this._logs];
  }
  
  /**
   * Clear all logs
   */
  clear() {
    this._logs = [];
    connectionLogs.set([]);
  }
}