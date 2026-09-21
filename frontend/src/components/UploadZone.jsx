import { useRef, useState } from "react";
import { uploadFile } from "../services/api";
import "./UploadZone.css";

// ── Constants ──────────────────────────────────────────────────
const ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".pdf", ".docx"];
const MAX_SIZE_MB = 20;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

const FORMAT_META = {
  ".csv":  { label: "CSV",  color: "#34d399" },
  ".xlsx": { label: "XLSX", color: "#60a5fa" },
  ".pdf":  { label: "PDF",  color: "#f87171" },
  ".docx": { label: "DOCX", color: "#a78bfa" },
};

// ── Helper ─────────────────────────────────────────────────────
function getExtension(filename) {
  return ("." + filename.split(".").pop()).toLowerCase();
}

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
}

// ── Component ──────────────────────────────────────────────────
export default function UploadZone({ onUploadSuccess, onReset }) {
  const [state, setState] = useState("idle");   // idle | dragover | uploading | success | error
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState(null);   // server response on success
  const [error, setError] = useState("");        // error message
  const inputRef = useRef(null);

  // ── Client-side validation ─────────────────────────────────
  function validateFile(file) {
    const ext = getExtension(file.name);
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `"${ext}" is not supported. Please upload a CSV, XLSX, PDF, or DOCX file.`;
    }
    if (file.size === 0) {
      return "The selected file is empty. Please choose a valid file.";
    }
    if (file.size > MAX_SIZE_BYTES) {
      return `File is too large (${humanSize(file.size)}). Maximum allowed size is ${MAX_SIZE_MB} MB.`;
    }
    return null; // valid
  }

  // ── Upload handler ─────────────────────────────────────────
  async function handleFile(file) {
    const validationError = validateFile(file);
    if (validationError) {
      setState("error");
      setError(validationError);
      return;
    }

    // Clear previous document/chat state when starting a new upload
    if (onReset) onReset();

    setState("uploading");
    setError("");
    setResult(null);

    try {
      const data = await uploadFile(file);
      setResult(data);
      setState("success");
      if (onUploadSuccess) onUploadSuccess(data);
    } catch (err) {
      setState("error");
      setError(err.message || "Upload failed. Please try again.");
    }
  }

  // ── Drag events ────────────────────────────────────────────
  function onDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }

  function onDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }

  function onDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  // ── File input change ──────────────────────────────────────
  function onInputChange(e) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // Reset input so the same file can be re-selected
    e.target.value = "";
  }

  function reset() {
    setState("idle");
    setError("");
    setResult(null);
    if (onReset) onReset();
  }

  // ── Render ─────────────────────────────────────────────────
  return (
    <section className="upload-zone" aria-label="File upload area">
      {/* ── Idle / Drag-over state ── */}
      {(state === "idle" || state === "dragover") && (
        <>
          <div
            className={`upload-zone__droparea${dragOver ? " upload-zone__droparea--active" : ""}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Drop a file here or click to browse"
            onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
          >
            <div className="upload-zone__icon" aria-hidden="true">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="24" fill={dragOver ? "rgba(99,102,241,0.2)" : "rgba(99,102,241,0.1)"} />
                <path
                  d="M24 32V20M24 20L19 25M24 20L29 25"
                  stroke={dragOver ? "#a5b4fc" : "#818cf8"}
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M16 33h16"
                  stroke={dragOver ? "#a5b4fc" : "#818cf8"}
                  strokeWidth="2"
                  strokeLinecap="round"
                  opacity="0.5"
                />
              </svg>
            </div>

            <div className="upload-zone__text">
              <p className="upload-zone__primary">
                {dragOver ? "Release to upload" : "Drop your file here"}
              </p>
              <p className="upload-zone__secondary">
                {dragOver ? "" : <>or <span className="upload-zone__browse">browse to upload</span></>}
              </p>
            </div>

            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.pdf,.docx"
              onChange={onInputChange}
              className="upload-zone__input"
              aria-hidden="true"
              tabIndex={-1}
            />
          </div>

          {/* Format badges */}
          <div className="upload-zone__formats" role="list" aria-label="Supported file formats">
            {Object.entries(FORMAT_META).map(([ext, { label, color }]) => (
              <div
                key={ext}
                className="format-badge"
                role="listitem"
                style={{ "--badge-color": color }}
              >
                <span className="format-badge__dot" aria-hidden="true" />
                <span className="format-badge__ext">{label}</span>
              </div>
            ))}
          </div>
          <p className="upload-zone__limit">Max file size: {MAX_SIZE_MB} MB</p>
        </>
      )}

      {/* ── Uploading state ── */}
      {state === "uploading" && (
        <div className="upload-state upload-state--uploading" role="status" aria-live="polite">
          <div className="upload-spinner" aria-hidden="true">
            <svg viewBox="0 0 50 50" width="48" height="48">
              <circle cx="25" cy="25" r="20" fill="none" stroke="rgba(99,102,241,0.2)" strokeWidth="4" />
              <circle
                cx="25" cy="25" r="20" fill="none"
                stroke="#818cf8" strokeWidth="4"
                strokeDasharray="80 45"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <p className="upload-state__title">Uploading…</p>
          <p className="upload-state__sub">Please wait</p>
        </div>
      )}

      {/* ── Success state ── */}
      {state === "success" && result && (
        <div className="upload-state upload-state--success" role="status" aria-live="polite">
          <div className="upload-state__icon upload-state__icon--success" aria-hidden="true">
            <svg viewBox="0 0 48 48" width="48" height="48" fill="none">
              <circle cx="24" cy="24" r="24" fill="rgba(34,197,94,0.15)" />
              <path d="M15 24l7 7 12-13" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <p className="upload-state__title">Upload successful!</p>

          <div className="upload-result">
            <div className="upload-result__row">
              <span className="upload-result__key">File</span>
              <span className="upload-result__val upload-result__filename" title={result.original_filename}>
                {result.original_filename}
              </span>
            </div>
            <div className="upload-result__row">
              <span className="upload-result__key">Type</span>
              <span
                className="upload-result__val upload-result__type"
                style={{ "--type-color": FORMAT_META[`.${result.file_type.toLowerCase()}`]?.color || "#818cf8" }}
              >
                {result.file_type}
              </span>
            </div>
            <div className="upload-result__row">
              <span className="upload-result__key">Size</span>
              <span className="upload-result__val">{result.file_size_display}</span>
            </div>
          </div>

          <button className="upload-btn upload-btn--reset" onClick={reset} type="button">
            Upload another file
          </button>
        </div>
      )}

      {/* ── Error state ── */}
      {state === "error" && (
        <div className="upload-state upload-state--error" role="alert" aria-live="assertive">
          <div className="upload-state__icon upload-state__icon--error" aria-hidden="true">
            <svg viewBox="0 0 48 48" width="48" height="48" fill="none">
              <circle cx="24" cy="24" r="24" fill="rgba(239,68,68,0.15)" />
              <path d="M17 17l14 14M31 17L17 31" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </div>
          <p className="upload-state__title">Upload failed</p>
          <p className="upload-state__message">{error}</p>
          <button className="upload-btn upload-btn--reset" onClick={reset} type="button">
            Try again
          </button>
        </div>
      )}
    </section>
  );
}
