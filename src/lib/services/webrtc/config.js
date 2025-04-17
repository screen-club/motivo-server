/**
 * WebRTC configuration constants and utilities
 */

// Quality options for video streaming
export const QUALITY_OPTIONS = [
  {
    id: "medium",
    label: "Standard (640×480)",
    width: 640,
    height: 480,
    recommended: true,
  },
  { id: "high", label: "High (1280×960)", width: 1280, height: 960 },
];

// Default ICE server configuration
export const getIceServers = () => {
  // Skip ICE servers on localhost for development
  if (
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1"
  ) {
    console.log("Running on localhost - skipping ICE servers");
    return [];
  }

  return [
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
  maxAttempts: 8, // Maximum reconnection attempts (increased)
  baseDelay: 3000, // Base delay in ms between reconnection attempts (increased)
  maxDelay: 15000, // Maximum delay in ms (increased)
  offerTimeout: 20000, // Timeout for offer creation in ms (increased slightly)
  connectionCheckInterval: 7500, // Interval for connection health checks in ms (increased)
};

// Helper for implementing exponential backoff
export function calculateBackoff(attempt, baseDelay, maxDelay) {
  const delay = Math.min(baseDelay * Math.pow(1.5, attempt), maxDelay);
  // Add jitter to avoid thundering herd problem
  return delay * (0.9 + Math.random() * 0.2);
}
