# WebRTC Service

This module provides a robust WebRTC implementation for video streaming with automatic reconnection handling.

## Architecture

The WebRTC service is organized into several components:

### Core Components

- **webrtcService.js**: Main service for managing WebRTC connections, exposing a public API
- **connectionState.js**: State management for connection status and logging
- **config.js**: Configuration constants and utility functions
- **index.js**: Public API entry point

### Features

- **Connection Management**: Handles establishing, maintaining, and cleaning up WebRTC connections
- **Auto Reconnection**: Implements exponential backoff reconnection strategy with configurable parameters
- **Quality Control**: Supports different video quality settings
- **Logging**: Comprehensive logging system for troubleshooting
- **Fullscreen Support**: Handles entering and exiting fullscreen mode
- **Error Handling**: Robust error handling for various connection scenarios

## Usage

```javascript
// Import the service and related utilities
import { 
  webrtcService, 
  isLoading, 
  hasStream, 
  connectionLogs, 
  currentQuality,
  qualityOptions 
} from './webrtc';

// Set video element
const videoElement = document.querySelector('video');
webrtcService.setVideoElement(videoElement);

// Change quality
webrtcService.setVideoQuality('high');

// Handle WebSocket state changes
websocketService.onReadyStateChange((isConnected) => {
  webrtcService.handleWebSocketStateChange(isConnected);
});

// Manual reconnection
webrtcService.restartConnection();

// Clean up
webrtcService.cleanup();
```

## Connection Stability Improvements

This implementation addresses several common WebRTC connection issues:

1. **Smart Reconnection Logic**: Uses exponential backoff with jitter to avoid overwhelming the server
2. **Connection Health Monitoring**: Periodically checks connection state and reconnects if needed
3. **ICE Configuration Optimization**: Configures ICE servers properly for NAT traversal
4. **Error Handling**: Comprehensive error handling for various failure modes
5. **Connection Timeouts**: Prevents connection attempts from hanging indefinitely
6. **WebSocket Dependency**: Properly integrates with WebSocket service for signaling

## Debug Capabilities

The WebRTC service includes several debugging features:

- Comprehensive logging with timestamp and log level
- Connection status reporting
- Direct WebSocket testing
- Visual indicators for connection state

These features help identify and troubleshoot connection issues in production.