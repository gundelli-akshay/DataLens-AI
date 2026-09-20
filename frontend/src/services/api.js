/**
 * services/api.js
 *
 * Central place for all backend API calls and authentication state.
 * Components import functions from here - they never call fetch() directly.
 */

const API_BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const TOKEN_KEY = "datalens_token";
const USER_KEY = "datalens_user";

// --- Auth Storage Helpers ---

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser() {
  const data = localStorage.getItem(USER_KEY);
  if (!data) return null;
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}

export function setAuthData(token, user) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("auth-changed"));
}

export function clearAuthData() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event("auth-changed"));
}

function getAuthHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders };
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

// --- Auth Endpoints ---

/**
 * POST /auth/signup - register new account with email/password.
 */
export async function signup({ email, password, fullName }) {
  const response = await fetch(`${API_BASE}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      full_name: fullName || undefined,
    }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Signup failed. Please try again.");
  }

  setAuthData(data.access_token, data.user);
  return data;
}

/**
 * POST /auth/login - authenticate with email and password.
 */
export async function login({ email, password }) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Invalid email or password.");
  }

  setAuthData(data.access_token, data.user);
  return data;
}

/**
 * POST /auth/google - authenticate with Google ID token.
 */
export async function loginWithGoogle(credential) {
  const response = await fetch(`${API_BASE}/auth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Google authentication failed.");
  }

  setAuthData(data.access_token, data.user);
  return data;
}

/**
 * GET /auth/me - fetch current authenticated user profile.
 */
export async function getMe() {
  const token = getAuthToken();
  if (!token) return null;

  const response = await fetch(`${API_BASE}/auth/me`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    clearAuthData();
    return null;
  }

  const data = await response.json();
  setAuthData(token, data.user);
  return data.user;
}


/**
 * GET /auth/config - fetch public authentication configuration (Google Client ID, etc.).
 */
export async function getAuthConfig() {
  try {
    const response = await fetch(`${API_BASE}/auth/config`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

// --- General API Endpoints ---

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
 * POST /upload/ - upload a single file (CSV, XLSX, PDF, DOCX).
 * Passes Authorization header if logged in.
 */
export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const headers = {};
  const token = getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}/upload/`, {
    method: "POST",
    headers,
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
 * POST /analyze/ - analyse a previously uploaded CSV or XLSX file.
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

/**
 * POST /ai/insights/ - generate AI insights from dataset analysis.
 */
export async function getAiInsights({ savedFilename, analysis } = {}) {
  const body = {};
  if (savedFilename) body.saved_filename = savedFilename;
  if (analysis) body.analysis = analysis;

  const response = await fetch(`${API_BASE}/ai/insights/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let detail = "Failed to generate AI insights.";
    try {
      const data = await response.json();
      if (data.detail) detail = data.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return response.json();
}

/**
 * POST /documents/index - chunk, embed, and index an uploaded PDF or DOCX file.
 */
export async function indexDocument(savedFilename) {
  const response = await fetch(`${API_BASE}/documents/index`, {
    method: "POST",
    headers: getAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ saved_filename: savedFilename }),
  });

  if (!response.ok) {
    let detail = "Failed to index document.";
    try {
      const data = await response.json();
      if (data.detail) detail = data.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return response.json();
}

/**
 * POST /documents/chat - ask a question grounded in an indexed PDF/DOCX document.
 */
export async function chatDocument({ question, filename, savedFilename, topK = 4 }) {
  const response = await fetch(`${API_BASE}/documents/chat`, {
    method: "POST",
    headers: getAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      question,
      filename: filename || savedFilename,
      saved_filename: savedFilename,
      top_k: topK,
    }),
  });

  if (!response.ok) {
    let detail = "Failed to answer document question.";
    try {
      const data = await response.json();
      if (data.detail) detail = data.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return response.json();
}

/**
 * GET /documents/my-documents - list documents owned by authenticated user.
 */
export async function getMyDocuments() {
  const response = await fetch(`${API_BASE}/documents/my-documents`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error("Failed to load user documents.");
  }

  return response.json();
}
