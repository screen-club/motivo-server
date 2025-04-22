/**
 * WebRTC configuration
 */

// Video quality options - optimized for performance
export const QUALITY_OPTIONS = [
  {
    id: "low",
    label: "Low (640×360)",
    width: 640,
    height: 360,
    recommended: false,
  },
  {
    id: "medium",
    label: "Standard (854×480)",
    width: 854,
    height: 480,
    recommended: true,
  },
  { 
    id: "high", 
    label: "High (1280×720)", 
    width: 1280, 
    height: 720,
    recommended: false,
  },
  { 
    id: "hd", 
    label: "HD (1920×1080)", 
    width: 1920, 
    height: 1080,
    recommended: false,
  },
];

// Connection configuration
export const CONNECTION_CONFIG = {
  maxAttempts: 10,           // Maximum reconnection attempts
  baseDelay: 2000,           // Base delay in ms between reconnection attempts
  maxDelay: 15000,           // Maximum delay in ms
  offerTimeout: 20000,       // Timeout for offer creation in ms
  connectionCheckInterval: 7500,  // Interval for connection health checks in ms
};

// Helper for implementing exponential backoff with jitter
export function calculateBackoff(attempt, baseDelay, maxDelay) {
  const delay = Math.min(baseDelay * Math.pow(1.5, attempt - 1), maxDelay);
  // Add jitter to avoid thundering herd problem
  return delay * (0.8 + Math.random() * 0.4); // 20% jitter
}

// ICE server configuration
export const getIceServers = () => {
  // Check if ICE servers should be used
  const useIce = import.meta.env.VITE_USE_ICE_SERVER !== "false";

  if (!useIce) {
    console.log("VITE_USE_ICE_SERVER is false - skipping ICE servers");
    return [];
  }

  console.log("Configuring ICE servers for WebRTC");
  
  // Build array of ICE servers
  const iceServers = [];
  
  // Add Google STUN servers for NAT traversal (public, reliable)
  const stunServers = [
    "stun:stun.l.google.com:19302",
    "stun:stun1.l.google.com:19302",
    "stun:stun2.l.google.com:19302"
  ];
  
  // Add custom STUN server if configured
  if (import.meta.env.VITE_STUN_URL) {
    stunServers.unshift(import.meta.env.VITE_STUN_URL);
  }
  
  // Add STUN servers
  iceServers.push({
    urls: stunServers
  });
  
  // Add TURN server if configured
  const turnUrl = import.meta.env.VITE_TURN_URL;
  const turnUsername = import.meta.env.VITE_TURN_USERNAME;
  const turnPassword = import.meta.env.VITE_TURN_PASSWORD;
  
  if (turnUrl && turnUsername && turnPassword) {
    // UDP TURN server
    iceServers.push({
      urls: turnUrl,
      username: turnUsername,
      credential: turnPassword
    });
    
    // Add TCP TURN server for restricted networks
    if (turnUrl.startsWith("turn:")) {
      iceServers.push({
        urls: `${turnUrl}?transport=tcp`,
        username: turnUsername,
        credential: turnPassword
      });
    }
  } else {
    // Fallback TURN server if none provided in env
    console.log("Using fallback TURN server configuration");
    iceServers.push({
      urls: "turn:51.159.163.145:3478",
      username: "admin",
      credential: "password"
    });
    
    // TCP fallback
    iceServers.push({
      urls: "turn:51.159.163.145:3478?transport=tcp",
      username: "admin",
      credential: "password"
    });
  }
  
  return iceServers;
};