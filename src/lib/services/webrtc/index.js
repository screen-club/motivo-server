/**
 * WebRTC module exports
 * 
 * This file serves as the main entry point for WebRTC functionality,
 * re-exporting the service and related utilities.
 */

// Re-export the service and state management
export { webrtcService } from './webrtcService.js';
export { isLoading, hasStream, connectionLogs, currentQuality } from './connectionState.js';

// Re-export configuration options
export { QUALITY_OPTIONS as qualityOptions } from './config.js';

// Export for debugging
export { CONNECTION_CONFIG, getIceServers } from './config.js';