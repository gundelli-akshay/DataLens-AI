/**
 * services/api.js
 *
 * Central place for all backend API calls.
 * Components import functions from here — they never call fetch() directly.
 */

const API_BASE = "/api";

/** GET /health */
export async function checkHealth() {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
  return response.json();
}

/** GET / */
export async function fetchApiInfo() {
  const response = await fetch(`${API_BASE}/`);
  if (!response.ok) throw new Error(`API info fetch failed: ${response.status}`);
  return response.json();
}

/**
 * POST /upload/ — upload a single file.
 * @param {File} file
 * @returns {Promise<{ status, original_filename, saved_filename, file_type, file_size_bytes, file_size_display }>}
 */
export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/upload/`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let detail = "Upload failed. Please try again.";
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return response.json();
}

/**
 * POST /analyze/ — analyse a previously uploaded CSV or XLSX file.
 *
 * @param {string} savedFilename - The UUID-prefixed filename returned by uploadFile().
 * @returns {Promise<AnalysisResult>} Structured analysis from Pandas.
 * @throws {Error} with a human-readable message from the backend.
 *
 * @typedef {Object} AnalysisResult
 * @property {"success"} status
 * @property {string}    filename
 * @property {"CSV"|"XLSX"} file_type
 * @property {{ rows: number, columns: number }} shape
 * @property {string[]} column_names
 * @property {Array<{
 *   name: string, dtype: string, category: string,
 *   missing_count: number, missing_pct: number, unique_count: number
 * }>} columns
 * @property {number} missing_total
 * @property {number} duplicate_rows
 * @property {Object} numeric_summary
 * @property {Object} categorical_summary
 */
export async function analyzeFile(savedFilename) {
  const response = await fetch(`${API_BASE}/analyze/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ saved_filename: savedFilename }),
  });

  if (!response.ok) {
    let detail = "Analysis failed. Please try again.";
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return response.json();
}
