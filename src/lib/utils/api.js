// src/lib/utils/api.js
export function getApiUrl() {
  // Use Vite's way of accessing environment variables
  // Ensure VITE_API_URL is set in your .env file
  const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5002"; // Default fallback
  return apiUrl;
}
