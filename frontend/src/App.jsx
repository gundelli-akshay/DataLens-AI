import { useState, useEffect } from "react";
import { useHealthCheck } from "./hooks/useHealthCheck";
import { analyzeFile, getStoredUser, clearAuthData, getMe } from "./services/api";
import Header from "./components/Header";
import UploadZone from "./components/UploadZone";
import ResultsPlaceholder from "./components/ResultsPlaceholder";
import AnalysisResults from "./components/AnalysisResults";
import DocumentChat from "./components/DocumentChat";
import AuthModal from "./components/AuthModal";
import UserMenuModal from "./components/UserMenuModal";
import SignOutModal from "./components/SignOutModal";
import LegalPage from "./components/LegalPage";
import "./App.css";

const ANALYSIS_TYPES = ["CSV", "XLSX"];

export default function App() {
  const apiStatus = useHealthCheck();

  // Route state (SPA routing supporting direct URLs and page refreshes)
  const [currentPath, setCurrentPath] = useState(() => window.location.pathname);

  // Authentication state
  const [user, setUser] = useState(() => getStoredUser());
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [userModalTab, setUserModalTab] = useState("profile");
  const [signOutModalOpen, setSignOutModalOpen] = useState(false);

  // Workspace and document state
  const [uploadResult, setUploadResult] = useState(null);
  const [analysisState, setAnalysisState] = useState("idle");
  const [analysisData, setAnalysisData] = useState(null);
  const [analysisError, setAnalysisError] = useState("");
  const [workspaceKey, setWorkspaceKey] = useState(0);

  const isDocChat = Boolean(uploadResult && !ANALYSIS_TYPES.includes(uploadResult.file_type));

  // Listen for browser navigation (back/forward)
  useEffect(() => {
    function handlePopState() {
      setCurrentPath(window.location.pathname);
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // Programmatic navigation updating URL and state
  function navigate(path) {
    if (window.location.pathname !== path) {
      window.history.pushState({}, "", path);
      setCurrentPath(path);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  // Update document title for workspace
  useEffect(() => {
    if (currentPath !== "/privacy" && currentPath !== "/terms") {
      document.title = "DataLens AI: Dataset Analytics & Document Intelligence";
    }
  }, [currentPath]);

  // Always show fresh workspace on initial mount
  useEffect(() => {
    handleResetUpload();
    setWorkspaceKey((prev) => prev + 1);
  }, []);

  // Synchronize auth state and verify session on load
  useEffect(() => {
    function handleAuthChange() {
      const u = getStoredUser();
      setUser(u);
      if (!u) {
        setUploadResult(null);
        setAnalysisData(null);
        setAnalysisError("");
        setAnalysisState("idle");
        setUserModalOpen(false);
        setWorkspaceKey((prev) => prev + 1);
      }
    }
    window.addEventListener("auth-changed", handleAuthChange);

    getMe().then((profile) => {
      if (profile) setUser(profile);
    }).catch(() => {});

    return () => window.removeEventListener("auth-changed", handleAuthChange);
  }, []);

  function handleResetUpload() {
    setUploadResult(null);
    setAnalysisData(null);
    setAnalysisError("");
    setAnalysisState("idle");
  }

  function handleRequestSignOut() {
    setSignOutModalOpen(true);
  }

  function handleConfirmSignOut() {
    clearAuthData();
    setUser(null);
    setUserModalOpen(false);
    setAuthModalOpen(false);
    setSignOutModalOpen(false);
    handleResetUpload();
    setWorkspaceKey((prev) => prev + 1);
  }

  function handleOpenUserMenu(tab) {
    setUserModalTab(tab || "profile");
    setUserModalOpen(true);
  }

  async function runTabularAnalysis(savedFilename) {
    setAnalysisState("loading");
    try {
      const result = await analyzeFile(savedFilename);
      setAnalysisData(result);
      setAnalysisState("success");
    } catch (err) {
      setAnalysisState("error");
      setAnalysisError(err.message || "Analysis failed. Please try again.");
    }
  }

  function handleDeleteDocument(deletedDoc) {
    if (!deletedDoc) return;
    const deletedId = deletedDoc.id || deletedDoc.document_id;
    const deletedSaved = deletedDoc.saved_filename;
    const currentSaved = uploadResult?.saved_filename;
    const currentId = uploadResult?.id || uploadResult?.document_id;

    if (
      (deletedId && currentId && deletedId === currentId) ||
      (deletedSaved && currentSaved && deletedSaved === currentSaved)
    ) {
      handleResetUpload();
    }
  }

  async function handleSelectDocument(doc) {
    if (!doc) return;
    const formattedDoc = {
      saved_filename: doc.saved_filename,
      original_filename: doc.original_filename || doc.saved_filename,
      file_type: doc.file_type || "PDF",
      file_size_bytes: doc.file_size_bytes,
      _ts: Date.now(),
    };

    setUploadResult(formattedDoc);
    setAnalysisData(null);
    setAnalysisError("");

    if (ANALYSIS_TYPES.includes(formattedDoc.file_type)) {
      await runTabularAnalysis(formattedDoc.saved_filename);
    } else {
      setAnalysisState("idle");
    }

    setTimeout(() => {
      const resultsEl = document.querySelector(".card--doc-chat") || document.querySelector(".card:nth-of-type(2)");
      if (resultsEl) {
        resultsEl.scrollIntoView({ behavior: "smooth" });
      }
    }, 100);
  }

  async function handleUploadSuccess(uploadData) {
    setUploadResult(uploadData);
    setAnalysisData(null);
    setAnalysisError("");

    if (!ANALYSIS_TYPES.includes(uploadData.file_type)) {
      setAnalysisState("idle");
      return;
    }

    await runTabularAnalysis(uploadData.saved_filename);
  }

  function renderResults() {
    if (analysisState === "loading") {
      return (
        <div className="analysis-loading" role="status" aria-live="polite">
          <div className="analysis-loading__spinner" aria-hidden="true">
            <svg viewBox="0 0 50 50" width="38" height="38">
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
          <p className="analysis-loading__text">Analysing dataset statistics and distributions...</p>
        </div>
      );
    }

    if (analysisState === "success" && analysisData) {
      return (
        <AnalysisResults
          data={analysisData}
          savedFilename={uploadResult?.saved_filename}
        />
      );
    }

    if (analysisState === "error") {
      return (
        <div className="analysis-error" role="alert">
          <p className="analysis-error__title">Analysis failed</p>
          <p className="analysis-error__msg">{analysisError}</p>
        </div>
      );
    }

    if (uploadResult && !ANALYSIS_TYPES.includes(uploadResult.file_type)) {
      return (
        <DocumentChat
          key={`${uploadResult.saved_filename}_${uploadResult._ts || ""}`}
          document={uploadResult}
          user={user}
          onRequireAuth={() => setAuthModalOpen(true)}
        />
      );
    }

    return <ResultsPlaceholder />;
  }

  return (
    <div className="app">
      <Header
        apiStatus={apiStatus}
        user={user}
        onNavigate={navigate}
        onOpenAuth={() => setAuthModalOpen(true)}
        onOpenUserMenu={handleOpenUserMenu}
        onSignOut={handleRequestSignOut}
      />

      {/* Route: /privacy */}
      {currentPath === "/privacy" && (
        <LegalPage type="privacy" onNavigate={navigate} />
      )}

      {/* Route: /terms */}
      {currentPath === "/terms" && (
        <LegalPage type="terms" onNavigate={navigate} />
      )}

      {/* Route: / (Default Workspace) */}
      {currentPath !== "/privacy" && currentPath !== "/terms" && (
        <main className="main">
          {/* Modern Hero Section */}
          <section className="hero" aria-labelledby="hero-title">
            <h1 id="hero-title" className="hero__title">
              Analyze datasets and query documents in one workspace
            </h1>
            <p className="hero__subtitle">
              Upload spreadsheets for automated statistics, distributions, and charts, or index documents to ask questions with verified citations.
            </p>
          </section>

          {/* Upload Card */}
          <div className="card">
            <div className="card__header-bar">
              <span className="card__title">Upload Dataset or Document</span>
              <span className="card__meta">CSV &middot; XLSX &middot; PDF &middot; DOCX (20 MB limit)</span>
            </div>
            <UploadZone
              key={workspaceKey}
              user={user}
              onRequireAuth={() => setAuthModalOpen(true)}
              onUploadSuccess={handleUploadSuccess}
              onReset={handleResetUpload}
            />
          </div>

          {/* Results / Analysis Card */}
          <div className={`card ${isDocChat ? "card--doc-chat" : ""}`}>
            {renderResults()}
          </div>
        </main>
      )}

      {/* Global Footer with Working Dedicated Route Links */}
      <footer className="footer">
        <div className="footer__content">
          <p className="footer__tagline">DataLens AI: Dataset Analytics and Document Intelligence</p>
          <nav className="footer__nav" aria-label="Legal navigation">
            <a
              href="/privacy"
              className={`footer__link ${currentPath === "/privacy" ? "footer__link--active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                navigate("/privacy");
              }}
            >
              Privacy Policy
            </a>
            <span className="footer__sep" aria-hidden="true">&middot;</span>
            <a
              href="/terms"
              className={`footer__link ${currentPath === "/terms" ? "footer__link--active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                navigate("/terms");
              }}
            >
              Terms of Service
            </a>
          </nav>
          <p className="footer__copyright">&copy; 2026 DataLens AI. All rights reserved.</p>
        </div>
      </footer>

      {/* Authentication Modal */}
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onSuccess={(loggedUser) => setUser(loggedUser)}
      />

      {/* User Menu Modal (Profile, Chat History, My Documents) */}
      <UserMenuModal
        isOpen={userModalOpen}
        initialTab={userModalTab}
        user={user}
        onClose={() => setUserModalOpen(false)}
        onSelectDocument={handleSelectDocument}
        onDeleteDocument={handleDeleteDocument}
        onSignOut={handleRequestSignOut}
      />

      {/* Sign Out Confirmation Modal */}
      <SignOutModal
        isOpen={signOutModalOpen}
        onClose={() => setSignOutModalOpen(false)}
        onConfirm={handleConfirmSignOut}
      />
    </div>
  );
}
