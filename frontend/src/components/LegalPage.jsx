import { useEffect } from "react";
import "./LegalPage.css";

export default function LegalPage({ type = "privacy", onNavigate }) {
  const isPrivacy = type === "privacy";

  useEffect(() => {
    document.title = isPrivacy
      ? "Privacy Policy - DataLens AI"
      : "Terms of Service - DataLens AI";
    window.scrollTo(0, 0);
  }, [isPrivacy]);

  return (
    <div className="legal-page">
      <div className="legal-page__container">
        {/* Navigation Breadcrumb / Switcher */}
        <div className="legal-page__topbar">
          <button
            type="button"
            className="legal-page__back-btn"
            onClick={() => onNavigate("/")}
            aria-label="Back to Workspace"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            Back to Workspace
          </button>

          <div className="legal-page__nav-toggle">
            <button
              type="button"
              className={`legal-page__toggle-btn ${isPrivacy ? "active" : ""}`}
              onClick={() => onNavigate("/privacy")}
            >
              Privacy Policy
            </button>
            <button
              type="button"
              className={`legal-page__toggle-btn ${!isPrivacy ? "active" : ""}`}
              onClick={() => onNavigate("/terms")}
            >
              Terms of Service
            </button>
          </div>
        </div>

        {/* Document Content */}
        <article className="legal-article">
          {isPrivacy ? (
            <>
              <header className="legal-article__header">
                <h1 className="legal-article__title">Privacy Policy</h1>
                <p className="legal-article__meta">Last updated: September 23, 2026</p>
                <p className="legal-article__lead">
                  This Privacy Policy describes how DataLens AI collects, processes, and protects information when you use our dataset analysis and document intelligence platform.
                </p>
              </header>

              <section className="legal-article__section">
                <h2>1. Service Overview</h2>
                <p>
                  DataLens AI provides computational statistical profiling for structured tabular files (CSV, XLSX) and semantic retrieval question answering for unstructured documents (PDF, DOCX). We process data solely to execute the analysis and queries you explicitly initiate.
                </p>
              </section>

              <section className="legal-article__section">
                <h2>2. Information We Collect and Process</h2>
                <p>We process the following categories of information:</p>
                <ul>
                  <li>
                    <strong>Account Information:</strong> When you create an account, we store your email address, full name (if provided), and a securely hashed password using standard bcrypt encryption. If you authenticate via Google Sign-In, we verify your identity token directly with Google Identity Services.
                  </li>
                  <li>
                    <strong>Uploaded Files:</strong> Datasets and documents uploaded to the platform are stored either in secure local server storage or in private cloud storage buckets (Supabase Storage) depending on environment deployment.
                  </li>
                  <li>
                    <strong>Extracted Text and Vector Embeddings:</strong> For PDF and Word documents, text is extracted into clean semantic chunks and indexed in-memory using vector embeddings to enable rapid similarity search during your session.
                  </li>
                  <li>
                    <strong>Chat and Query History:</strong> Questions submitted during document chat sessions and their corresponding answers are stored to preserve your session history.
                  </li>
                </ul>
              </section>

              <section className="legal-article__section">
                <h2>3. AI Processing and Third-Party Services</h2>
                <p>
                  To generate narrative summaries from computed statistics and formulate answers from document excerpts, relevant structured metrics or retrieved context chunks are transmitted over encrypted HTTPS to our configured AI service providers. DataLens AI utilizes Google Gemini as its primary large language model provider, with Groq configured as a fallback provider for resilient inference.
                </p>
                <ul>
                  <li>Google Gemini and Groq process inference prompts ephemerally to generate completions.</li>
                  <li>Your uploaded files, dataset metrics, and document queries are not used by DataLens AI or its LLM providers to train artificial intelligence models.</li>
                  <li>We do not sell, rent, or monetize your datasets, documents, or personal credentials.</li>
                </ul>
              </section>

              <section className="legal-article__section">
                <h2>4. Data Ownership and Permanent Deletion</h2>
                <p>
                  You retain full ownership of all data, spreadsheets, and documents uploaded to DataLens AI. You may delete any uploaded document and its associated query history permanently at any time via the user account menu. Upon deletion:
                </p>
                <ul>
                  <li>The database record is deleted immediately.</li>
                  <li>The stored file object is permanently removed from storage.</li>
                  <li>All associated chat messages and in-memory vector representations are purged.</li>
                </ul>
              </section>

              <section className="legal-article__section">
                <h2>5. Security Standards</h2>
                <p>
                  We implement technical and operational safeguards to protect your data, including HTTPS transport encryption for all web and API traffic, parameterized database queries to prevent injection attacks, and strict JSON Web Token (JWT) session validation for protected endpoints.
                </p>
              </section>
            </>
          ) : (
            <>
              <header className="legal-article__header">
                <h1 className="legal-article__title">Terms of Service</h1>
                <p className="legal-article__meta">Last updated: September 23, 2026</p>
                <p className="legal-article__lead">
                  These Terms of Service govern your access to and use of DataLens AI. By using the platform, you agree to these terms.
                </p>
              </header>

              <section className="legal-article__section">
                <h2>1. Acceptance of Terms</h2>
                <p>
                  By creating an account, uploading files, or otherwise accessing DataLens AI, you agree to be bound by these Terms of Service. If you do not agree, you must discontinue use of the service.
                </p>
              </section>

              <section className="legal-article__section">
                <h2>2. Description of Service and Usage Limits</h2>
                <p>
                  DataLens AI provides automated dataset analytics and document-grounded question answering. Service limits include:
                </p>
                <ul>
                  <li><strong>Supported File Formats:</strong> Tabular datasets in CSV and XLSX formats, and text documents in PDF and DOCX formats.</li>
                  <li><strong>File Size Threshold:</strong> Maximum file size is strictly 20 MB per upload.</li>
                  <li><strong>Authentication:</strong> File uploads, dataset analysis, and document chat require an authenticated user account.</li>
                </ul>
              </section>

              <section className="legal-article__section">
                <h2>3. User Responsibilities</h2>
                <p>
                  You are responsible for ensuring that you possess all necessary rights, licenses, and permissions for any dataset or document uploaded to the platform. You agree not to upload:
                </p>
                <ul>
                  <li>Malicious files, executable binaries, or content designed to exploit vulnerabilities.</li>
                  <li>Unlawful, defamatory, or infringing material.</li>
                  <li>Content that violates third-party intellectual property or contractual confidentiality obligations.</li>
                </ul>
              </section>

              <section className="legal-article__section">
                <h2>4. Intellectual Property and Content Rights</h2>
                <p>
                  You retain all existing rights, title, and interest in and to the files you upload. DataLens AI claims no intellectual property ownership over user datasets, uploaded documents, or generated query outputs.
                </p>
              </section>

              <section className="legal-article__section">
                <h2>5. Analytical Disclaimers and Limitations</h2>
                <p>
                  DataLens AI provides analytical statistics, automated charts, and language model completions for informational and analytical assistance on an "as is" and "as available" basis.
                </p>
                <ul>
                  <li>While statistical computations are deterministic, natural language summaries and answers generated by language models should be verified against source citations.</li>
                  <li>DataLens AI makes no guarantees of uninterrupted service availability, error-free processing, or fitness for high-stakes regulatory or financial audit purposes.</li>
                </ul>
              </section>

              <section className="legal-article__section">
                <h2>6. Termination and Account Deletion</h2>
                <p>
                  You may stop using DataLens AI at any time. You can delete your uploaded files and chat sessions directly from the user interface. We reserve the right to suspend or restrict access to accounts that abuse API endpoints, exceed rate limits, or violate these terms.
                </p>
              </section>
            </>
          )}
        </article>
      </div>
    </div>
  );
}
