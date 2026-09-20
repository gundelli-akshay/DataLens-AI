import { useState } from "react";
import { useHealthCheck } from "./hooks/useHealthCheck";
import { analyzeFile } from "./services/api";
import Header from "./components/Header";
import UploadZone from "./components/UploadZone";
import ResultsPlaceholder from "./components/ResultsPlaceholder";
import AnalysisResults from "./components/AnalysisResults";
import "./App.css";

// ── Analysis states: idle | loading | success | error ──────────
const ANALYSIS_TYPES = ["CSV", "XLSX"];

export default function App() {
  const apiStatus = useHealthCheck();

  // Last upload response from /upload/
  const [uploadResult, setUploadResult] = useState(null);

  // Analysis state machine
  const [analysisState, setAnalysisState]   = useState("idle");
  const [analysisData,  setAnalysisData]    = useState(null);
  const [analysisError, setAnalysisError]   = useState("");

  // ── Called by UploadZone on every successful upload ──────────
  async function handleUploadSuccess(uploadData) {
    setUploadResult(uploadData);
    setAnalysisData(null);
    setAnalysisError("");

    // Only analyse CSV and XLSX — skip PDF/DOCX for now
    if (!ANALYSIS_TYPES.includes(uploadData.file_type)) {
      setAnalysisState("idle");
      return;
    }

    setAnalysisState("loading");
    try {
      const result = await analyzeFile(uploadData.saved_filename);
      setAnalysisData(result);
      setAnalysisState("success");
    } catch (err) {
      setAnalysisState("error");
      setAnalysisError(err.message || "Analysis failed. Please try again.");
    }
  }

  // ── Decide what to render in the results card ────────────────
  function renderResults() {
    // Analysis running
    if (analysisState === "loading") {
      return (
        <div className="analysis-loading" role="status" aria-live="polite">
          <div className="analysis-loading__spinner" aria-hidden="true">
            <svg viewBox="0 0 50 50" width="40" height="40">
              <circle cx="25" cy="25" r="20" fill="none" stroke="rgba(99,102,241,0.2)" strokeWidth="4" />
              <circle cx="25" cy="25" r="20" fill="none" stroke="#818cf8" strokeWidth="4"
                strokeDasharray="80 45" strokeLinecap="round" />
            </svg>
          </div>
          <p className="analysis-loading__text">Analysing dataset…</p>
        </div>
      );
    }

    // Analysis success
    if (analysisState === "success" && analysisData) {
      return <AnalysisResults data={analysisData} />;
    }

    // Analysis error
    if (analysisState === "error") {
      return (
        <div className="analysis-error" role="alert">
          <p className="analysis-error__title">Analysis failed</p>
          <p className="analysis-error__msg">{analysisError}</p>
        </div>
      );
    }

    // PDF/DOCX uploaded — no analysis yet
    if (uploadResult && !ANALYSIS_TYPES.includes(uploadResult.file_type)) {
      return (
        <div className="analysis-document" role="status">
          <p className="analysis-document__icon" aria-hidden="true">📄</p>
          <p className="analysis-document__title">
            {uploadResult.file_type} uploaded successfully
          </p>
          <p className="analysis-document__msg">
            Document analysis (PDF&nbsp;/&nbsp;DOCX) will be available in a future step.
          </p>
        </div>
      );
    }

    // Default: nothing uploaded yet
    return <ResultsPlaceholder uploadedFile={uploadResult} />;
  }

  return (
    <div className="app">
      <Header apiStatus={apiStatus} />

      <main className="main">
        {/* ── Hero ── */}
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero__badge">
            <span className="hero__badge-dot" aria-hidden="true" />
            AI-Powered Analysis
          </div>
          <h1 id="hero-title" className="hero__title">
            Turn your files into{" "}
            <span className="hero__title-accent">instant insights</span>
          </h1>
          <p className="hero__subtitle">
            Upload a CSV or XLSX file — DataLens AI will analyse your data,
            show statistics, and prepare it for AI-powered Q&amp;A.
          </p>
        </section>

        {/* ── Upload ── */}
        <div className="card">
          <div className="card__label">Step 1 — Upload a file</div>
          <UploadZone onUploadSuccess={handleUploadSuccess} />
        </div>

        {/* ── Results / Analysis ── */}
        <div className="card">
          {renderResults()}
        </div>
      </main>

      <footer className="footer">
        <p>DataLens AI · Portfolio Project · Built with FastAPI &amp; React</p>
      </footer>
    </div>
  );
}
