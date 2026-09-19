/**
 * services/api.js
 *
 * Central place for all backend API calls.
 * Components import functions from here — they never call fetch() directly.
 *
 * All URLs use the /api prefix, which Vite''s dev proxy forwards
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

/**
 * POST /upload/ — upload a single file.
 *
 * @param {File} file - The File object from the input or drop event.
 * @returns {Promise<{
 *   status: string,
 *   original_filename: string,
 *   saved_filename: string,
 *   file_type: string,
 *   file_size_bytes: number,
 *   file_size_display: string,
 * }>}
 * @throws {Error} with a human-readable message from the backend.
 */
export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/upload/`, {
    method: "POST",
    body: formData,
    // Do NOT set Content-Type manually — the browser sets it automatically
    // with the correct multipart boundary.
  });

  if (!response.ok) {
    // Extract the backend error message for display
    let detail = "Upload failed. Please try again.";
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      // ignore JSON parse failure
    }
    throw new Error(detail);
  }

  return response.json();
}
