import { useHealthCheck } from "./hooks/useHealthCheck";
import Header from "./components/Header";
import UploadZone from "./components/UploadZone";
import ResultsPlaceholder from "./components/ResultsPlaceholder";
import "./App.css";

export default function App() {
  // Check if the FastAPI backend is reachable
  const apiStatus = useHealthCheck();

  return (
    <div className="app">
      <Header apiStatus={apiStatus} />

      <main className="main">
        {/* ── Hero ──────────────────────────────── */}
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
            Upload a CSV, XLSX, PDF, or DOCX — DataLens AI will analyse your
            data, generate charts, and answer your questions automatically.
          </p>
        </section>

        {/* ── Upload ────────────────────────────── */}
        <div className="card">
          <div className="card__label">Step 1 — Upload a file</div>
          <UploadZone />
        </div>

        {/* ── Results ───────────────────────────── */}
        <div className="card">
          <ResultsPlaceholder />
        </div>
      </main>

      <footer className="footer">
        <p>DataLens AI · Portfolio Project · Built with FastAPI &amp; React</p>
      </footer>
    </div>
  );
}
