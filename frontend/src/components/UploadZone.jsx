import { useRef, useState } from "react";
import { uploadFile } from "../services/api";
import "./UploadZone.css";

const ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".pdf", ".docx"];
const MAX_SIZE_MB = 20;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

function getExtension(filename) {
  return ("." + filename.split(".").pop()).toLowerCase();
}

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
}

export default function UploadZone({ user, onRequireAuth, onUploadSuccess, onReset }) {
  const [state, setState] = useState("idle"); // idle | dragover | uploading | success | error
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  function validateFile(file) {
    const ext = getExtension(file.name);
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `"${ext}" is not supported. Please upload a CSV, XLSX, PDF, or DOCX file.`;
    }
    if (file.size === 0) {
      return "The selected file is empty. Please choose a valid file.";
    }
    if (file.size > MAX_SIZE_BYTES) {
      return `File exceeds maximum allowed size (${humanSize(file.size)}). Limit is ${MAX_SIZE_MB} MB.`;
    }
    return null;
  }

  async function handleFile(file) {
    if (!user) {
      if (onRequireAuth) onRequireAuth();
      return;
    }

    const validationError = validateFile(file);
    if (validationError) {
      setState("error");
      setError(validationError);
      return;
    }

    if (onReset) onReset();

    setState("uploading");
    setError("");
    setResult(null);

    try {
      const data = await uploadFile(file);
      setResult(data);
      setState("success");
      if (onUploadSuccess) {
        onUploadSuccess(data);
      }
    } catch (err) {
      setState("error");
      setError(err.message || "An unexpected error occurred during upload. Please try again.");
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!dragOver) setDragOver(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget.contains(e.relatedTarget)) return;
    setDragOver(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);

    if (!user) {
      if (onRequireAuth) onRequireAuth();
      return;
    }

    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  }

  function handleInputChange(e) {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
    e.target.value = "";
  }

  function handleClick() {
    if (!user) {
      if (onRequireAuth) onRequireAuth();
      return;
    }
    inputRef.current?.click();
  }

  function handleReset() {
    setState("idle");
    setResult(null);
    setError("");
    if (onReset) onReset();
  }

  return (
    <div className="upload-zone" aria-label="File upload section">
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.pdf,.docx"
        onChange={handleInputChange}
        className="upload-zone__input"
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* State: IDLE / DRAGOVER */}
      {(state === "idle" || state === "dragover") && (
        <div
          className={`upload-zone__droparea ${dragOver ? "upload-zone__droparea--active" : ""}`}
          onClick={handleClick}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          role="button"
          tabIndex={0}
          aria-label="Upload file by dropping or browsing"
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              handleClick();
            }
          }}
        >
          <div className="upload-zone__icon-box" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>

          <div className="upload-zone__copy">
            <p className="upload-zone__headline">
              Drag and drop your file here, or{" "}
              <span className="upload-zone__browse-action">browse from device</span>
            </p>
            <p className="upload-zone__subline">
              Spreadsheets or reference documents up to 20 MB
            </p>
          </div>

          <div className="upload-zone__formats-bar" aria-label="Supported file categories">
            <div className="upload-zone__format-group">
              <span className="upload-zone__format-label">Datasets</span>
              <span className="upload-zone__format-pill upload-zone__format-pill--tabular">CSV</span>
              <span className="upload-zone__format-pill upload-zone__format-pill--tabular">XLSX</span>
            </div>
            <span className="upload-zone__formats-divider" aria-hidden="true">&middot;</span>
            <div className="upload-zone__format-group">
              <span className="upload-zone__format-label">Documents</span>
              <span className="upload-zone__format-pill upload-zone__format-pill--doc">PDF</span>
              <span className="upload-zone__format-pill upload-zone__format-pill--doc">DOCX</span>
            </div>
          </div>
        </div>
      )}

      {/* State: UPLOADING */}
      {state === "uploading" && (
        <div className="upload-zone__status upload-zone__status--uploading" role="status" aria-live="polite">
          <div className="upload-zone__spinner" aria-hidden="true">
            <svg viewBox="0 0 50 50" width="36" height="36">
              <circle
                cx="25"
                cy="25"
                r="20"
                fill="none"
                stroke="rgba(2, 132, 199, 0.2)"
                strokeWidth="3.5"
              />
              <circle
                cx="25"
                cy="25"
                r="20"
                fill="none"
                stroke="#0284c7"
                strokeWidth="3.5"
                strokeDasharray="80 45"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <p className="upload-zone__status-title">Processing file</p>
          <p className="upload-zone__status-desc">Parsing contents and validating data schema...</p>
        </div>
      )}

      {/* State: SUCCESS */}
      {state === "success" && result && (
        <div className="upload-zone__status upload-zone__status--success" role="status" aria-live="polite">
          <div className="upload-zone__file-card">
            <div className="upload-zone__file-icon" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
            </div>
            <div className="upload-zone__file-details">
              <span className="upload-zone__file-name" title={result.original_filename}>
                {result.original_filename}
              </span>
              <div className="upload-zone__file-meta">
                <span className="upload-zone__file-badge">{result.file_type}</span>
                <span className="upload-zone__file-size">{humanSize(result.file_size_bytes)}</span>
              </div>
            </div>
            <button
              type="button"
              className="upload-zone__replace-btn"
              onClick={handleReset}
              aria-label="Upload a different file"
            >
              Replace File
            </button>
          </div>
        </div>
      )}

      {/* State: ERROR */}
      {state === "error" && (
        <div className="upload-zone__status upload-zone__status--error" role="alert">
          <div className="upload-zone__error-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <div className="upload-zone__error-text">
            <p className="upload-zone__status-title">Upload Failed</p>
            <p className="upload-zone__status-desc">{error}</p>
          </div>
          <button
            type="button"
            className="upload-zone__replace-btn"
            onClick={handleReset}
          >
            Try Again
          </button>
        </div>
      )}
    </div>
  );
}
