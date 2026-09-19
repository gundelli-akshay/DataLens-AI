/**
 * services/api.js
 *
 * Central place for all backend API calls.
 * Components import functions from here — they never call fetch() directly.
 *
 * All URLs use the /api prefix, which Vite's dev proxy forwards
 * to http://localhost:8000. In production, point VITE_API_URL at your server.
 */

const API_BASE = "/api";

/**
 * GET /health — confirm the API is reachable.
 * @returns {Promise<{ status: string, message: string }>}
 */
export async function checkHealth() {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}

/**
 * GET / — fetch root API info.
 * @returns {Promise<{ app: string, version: string, status: string }>}
 */
export async function fetchApiInfo() {
  const response = await fetch(`${API_BASE}/`);
  if (!response.ok) {
    throw new Error(`API info fetch failed: ${response.status}`);
  }
  return response.json();
}
