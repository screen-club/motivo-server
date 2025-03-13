/**
 * WebRTC configuration constants and utilities
 */

// Quality options for video streaming
export const QUALITY_OPTIONS = [
  { id: "medium", label: "Standard (640×480)", width: 640, height: 480, recommended: true },
  { id: "high", label: "High (1280×960)", width: 1280, height: 960 },
];

// Default ICE server configuration
export const getIceServers = () => {
  return [
    // Google's public STUN servers
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },

    // Project-specific STUN server
    { urls: "stun:51.159.163.145:3478" },

    // Project-specific TURN server
    {
      urls: "turn:51.159.163.145:3478",
      username: "admin",
      credential: "password",
    },

    // Project-specific TURN over TCP (helps with strict firewalls)
    {
      urls: "turn:51.159.163.145:3478?transport=tcp",
      username: "admin",
      credential: "password",
    },

    // Environment variable TURN servers if available
    ...(import.meta.env.VITE_TURN_URL &&
    import.meta.env.VITE_TURN_USERNAME &&
    import.meta.env.VITE_TURN_PASSWORD
      ? [
          {
            urls: import.meta.env.VITE_TURN_URL,
            username: import.meta.env.VITE_TURN_USERNAME,
            credential: import.meta.env.VITE_TURN_PASSWORD,
          },
          {
            urls: `${import.meta.env.VITE_TURN_URL}?transport=tcp`,
            username: import.meta.env.VITE_TURN_USERNAME,
            credential: import.meta.env.VITE_TURN_PASSWORD,
          },
        ]
      : []),

    // Custom STUN server if defined
    ...(import.meta.env.VITE_STUN_URL
      ? [{ urls: import.meta.env.VITE_STUN_URL }]
      : []),
  ];
};

// Connection retry configuration
export const CONNECTION_CONFIG = {
  maxAttempts: 5,               // Maximum reconnection attempts
  baseDelay: 2000,              // Base delay in ms between reconnection attempts
  maxDelay: 10000,              // Maximum delay in ms
  offerTimeout: 15000,          // Timeout for offer creation in ms
  connectionCheckInterval: 5000 // Interval for connection health checks in ms
};

// Helper for implementing exponential backoff
export function calculateBackoff(attempt, baseDelay, maxDelay) {
  const delay = Math.min(
    baseDelay * Math.pow(1.5, attempt),
    maxDelay
  );
  // Add jitter to avoid thundering herd problem
  return delay * (0.9 + Math.random() * 0.2);
}