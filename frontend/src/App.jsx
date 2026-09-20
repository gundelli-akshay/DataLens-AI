import { useState, useEffect } from "react";
import { useHealthCheck } from "./hooks/useHealthCheck";
import { analyzeFile, getStoredUser, clearAuthData, getMe } from "./services/api";
import Header from "./components/Header";
import UploadZone from "./components/UploadZone";
import ResultsPlaceholder from "./components/ResultsPlaceholder";
import AnalysisResults from "./components/AnalysisResults";
import DocumentChat from "./components/DocumentChat";
import AuthModal from "./components/AuthModal";
import "./App.css";

const ANALYSIS_TYPES = ["CSV", "XLSX"];

export default function App() {
  const apiStatus = useHealthCheck();

  // Authentication state
  const [user, setUser] = useState(() => getStoredUser());
  const [authModalOpen, setAuthModalOpen] = useState(false);

  // Synchronize auth state and verify session on load
  useEffect(() => {
    function handleAuthChange() {
      setUser(getStoredUser());
    }
    window.addEventListener("auth-changed", handleAuthChange);

    // Verify token validity with backend
    getMe().then((profile) => {
      if (profile) setUser(profile);
    }).catch(() => {});

    return () => window.removeEventListener("auth-changed", handleAuthChange);
  }, []);

  // Last upload response from /upload/
  const [uploadResult, setUploadResult] = useState(null);

  // Analysis state machine
  const [analysisState, setAnalysisState] = useState("idle");
  const [analysisData, setAnalysisData] = useState(null);
  const [analysisError, setAnalysisError] = useState("");

  // Called by UploadZone on every successful upload
  async function handleUploadSuccess(uploadData) {
    setUploadResult(uploadData);
    setAnalysisData(null);
    setAnalysisError("");

    // Only analyse CSV and XLSX - skip PDF/DOCX for tabular analysis
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

  // Decide what to render in the results card
  function renderResults() {
    // Analysis running
    if (analysisState === "loading") {
      return (
        <div className="analysis-loading" role="status" aria-live="polite">
          <div className="analysis-loading__spinner" aria-hidden="true">
            <svg viewBox="0 0 50 50" width="40" height="40">
              <circle
                cx="25"
                cy="25"
                r="20"
                fill="none"
                stroke="rgba(99,102,241,0.2)"
                strokeWidth="4"
              />
              <circle
                cx="25"
                cy="25"
                r="20"
                fill="none"
                stroke="#818cf8"
                strokeWidth="4"
                strokeDasharray="80 45"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <p className="analysis-loading__text">Analysing dataset...</p>
        </div>
      );
    }

    // Analysis success
    if (analysisState === "success" && analysisData) {
      return (
        <AnalysisResults
          data={analysisData}
          savedFilename={uploadResult?.saved_filename}
        />
      );
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

    // PDF/DOCX uploaded -> Unified AI RAG Chat
    if (uploadResult && !ANALYSIS_TYPES.includes(uploadResult.file_type)) {
      return (
        <DocumentChat
          document={uploadResult}
          user={user}
          onRequireAuth={() => setAuthModalOpen(true)}
        />
      );
    }

    // Default: nothing uploaded yet
    return <ResultsPlaceholder uploadedFile={uploadResult} />;
  }

  return (
    <div className="app">
      <Header
        apiStatus={apiStatus}
        user={user}
        onOpenAuth={() => setAuthModalOpen(true)}
        onSignOut={() => {
          clearAuthData();
          setUser(null);
        }}
      />

      <main className="main">
        {/* Hero */}
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero__badge">
            <span className="hero__badge-dot" aria-hidden="true" />
            AI-Powered Analysis & Documents
          </div>
          <h1 id="hero-title" className="hero__title">
            Turn your files into{" "}
            <span className="hero__title-accent">instant insights</span>
          </h1>
          <p className="hero__subtitle">
            Upload CSV/XLSX for automated statistics, charts, and Groq AI insights,
            or upload PDF/DOCX to chat grounded in your document context.
          </p>
        </section>

        {/* Upload Card */}
        <div className="card">
          <div className="card__label">Step 1 - Upload a file</div>
          <UploadZone onUploadSuccess={handleUploadSuccess} />
        </div>

        {/* Results / Analysis Card */}
        <div className="card">{renderResults()}</div>
      </main>

      <footer className="footer">
        <p>DataLens AI &bull; Portfolio Project &bull; Built with FastAPI &amp; React</p>
      </footer>

      {/* Authentication Modal */}
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onSuccess={(loggedUser) => setUser(loggedUser)}
      />
    </div>
  );
}
