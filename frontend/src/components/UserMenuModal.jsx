import { useState, useEffect } from "react";
import { getUserHistory, deleteDocument } from "../services/api";
import "./UserMenuModal.css";

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(isoString) {
  if (!isoString) return "Recently";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "Recently";
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "Recently";
  }
}

export default function UserMenuModal({
  isOpen,
  initialTab = "profile",
  user,
  onClose,
  onSelectDocument,
  onSignOut,
}) {
  const [activeTab, setActiveTab] = useState(initialTab === "documents" ? "history" : initialTab);
  const [historyList, setHistoryList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab === "documents" ? "history" : initialTab);
      setError("");
      setConfirmDeleteId(null);
    }
  }, [isOpen, initialTab]);

  useEffect(() => {
    if (!isOpen) return;
    let isMounted = true;

    if (activeTab === "history") {
      setLoading(true);
      setError("");
      getUserHistory()
        .then((res) => {
          if (isMounted) {
            setHistoryList(res.history || []);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (isMounted) {
            setError(err.message || "Failed to load history.");
            setLoading(false);
          }
        });
    }

    return () => {
      isMounted = false;
    };
  }, [isOpen, activeTab]);

  // Handle ESC key to close modal
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  async function handleDelete(docId) {
    if (!docId || deletingId) return;
    setDeletingId(docId);
    try {
      await deleteDocument(docId);
      setHistoryList((prev) => prev.filter((item) => (item.id || item.document_id) !== docId));
      setConfirmDeleteId(null);
    } catch (err) {
      setError(err.message || "Failed to delete document.");
    } finally {
      setDeletingId(null);
    }
  }

  if (!isOpen) return null;

  const initial = (user?.full_name || user?.email || "U").charAt(0).toUpperCase();

  return (
    <div className="user-modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="user-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header with 2 Tabs: Profile and History */}
        <div className="user-modal__header">
          <div className="user-modal__nav">
            <button
              type="button"
              className={`user-modal__tab ${activeTab === "profile" ? "active" : ""}`}
              onClick={() => setActiveTab("profile")}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              Profile
            </button>
            <button
              type="button"
              className={`user-modal__tab ${activeTab === "history" ? "active" : ""}`}
              onClick={() => setActiveTab("history")}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              History
            </button>
          </div>
          <button
            type="button"
            className="user-modal__close-btn"
            onClick={onClose}
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <div className="user-modal__body">
          {error && (
            <div className="user-modal__error" role="alert">
              <span>{error}</span>
            </div>
          )}

          {/* TAB 1: PROFILE */}
          {activeTab === "profile" && (
            <div className="user-modal__profile">
              <div className="user-modal__profile-card">
                <div className="user-modal__avatar">{initial}</div>
                <div className="user-modal__profile-main">
                  <h3 className="user-modal__name">{user?.full_name || "DataLens User"}</h3>
                  <p className="user-modal__email">{user?.email}</p>
                </div>
              </div>

              <div className="user-modal__details-grid">
                <div className="user-modal__detail-item">
                  <span className="user-modal__detail-label">Authentication Provider</span>
                  <div className="user-modal__detail-value">
                    {user?.auth_provider === "google" ? (
                      <span className="user-modal__provider-badge user-modal__provider-badge--google">
                        Google Account
                      </span>
                    ) : (
                      <span className="user-modal__provider-badge user-modal__provider-badge--email">
                        Email & Password
                      </span>
                    )}
                  </div>
                </div>

                <div className="user-modal__detail-item">
                  <span className="user-modal__detail-label">Account Created</span>
                  <span className="user-modal__detail-text">
                    {formatDate(user?.created_at)}
                  </span>
                </div>
              </div>

              <div className="user-modal__profile-actions">
                <button
                  type="button"
                  className="user-modal__signout-btn"
                  onClick={() => {
                    onClose();
                    onSignOut();
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                  Sign Out
                </button>
              </div>
            </div>
          )}

          {/* TAB 2: UNIFIED HISTORY */}
          {activeTab === "history" && (
            <div className="user-modal__history">
              {loading ? (
                <div className="user-modal__loading">
                  <div className="user-modal__spinner" />
                  <p>Loading your history...</p>
                </div>
              ) : historyList.length === 0 ? (
                <div className="user-modal__empty">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                  <p className="user-modal__empty-title">No history yet</p>
                  <p className="user-modal__empty-desc">
                    Upload a CSV, XLSX, PDF, or DOCX file to analyze data or chat with documents and review your work here.
                  </p>
                </div>
              ) : (
                <div className="user-modal__history-list">
                  {historyList.map((item) => {
                    const isTabular = ["CSV", "XLSX"].includes((item.file_type || "").toUpperCase());
                    const qCount = item.question_count || 0;
                    const docId = item.id || item.document_id;
                    const docName = item.original_filename || item.filename || "Document";
                    const fileType = (item.file_type || (isTabular ? "CSV" : "PDF")).toUpperCase();
                    const isConfirming = confirmDeleteId === docId;
                    const isThisDeleting = deletingId === docId;

                    return (
                      <div key={docId} className="user-modal__history-item">
                        {/* Header: Document Type Badge, Filename, Timestamp */}
                        <div className="user-modal__history-header">
                          <div className="user-modal__history-doc">
                            <span className={`user-modal__doc-badge user-modal__doc-badge--${fileType.toLowerCase()}`}>
                              {fileType}
                            </span>
                            <span className="user-modal__doc-name" title={docName}>
                              {docName}
                            </span>
                          </div>
                          <span className="user-modal__history-time">
                            {formatDate(item.last_activity || item.uploaded_at)}
                          </span>
                        </div>

                        {/* Content Area: Differentiated by Document vs Tabular */}
                        {!isTabular ? (
                          /* PDF / DOCX: Question count & latest Q&A preview */
                          <div className="user-modal__history-content">
                            {qCount > 0 ? (
                              <>
                                {item.latest_question && (
                                  <p className="user-modal__history-q">
                                    <strong>Latest Q:</strong> {item.latest_question}
                                  </p>
                                )}
                                {(item.latest_preview || item.latest_answer) && (
                                  <p className="user-modal__history-a">
                                    <strong>A:</strong> {item.latest_preview || item.latest_answer}
                                  </p>
                                )}
                              </>
                            ) : (
                              <p className="user-modal__history-empty-chat">
                                Document indexed and ready for grounded Q&A. No questions asked yet.
                              </p>
                            )}
                          </div>
                        ) : (
                          /* CSV / XLSX: Upload date & Analysis/AI Insights availability */
                          <div className="user-modal__history-content">
                            <div className="user-modal__tabular-meta">
                              <span className="user-modal__tabular-size">
                                {formatBytes(item.file_size_bytes)}
                              </span>
                              <span className="user-modal__tabular-dot">•</span>
                              <span className="user-modal__tabular-uploaded">
                                Uploaded {formatDate(item.uploaded_at)}
                              </span>
                              <span className="user-modal__tabular-dot">•</span>
                              {item.has_insights ? (
                                <span className="user-modal__insights-tag user-modal__insights-tag--ready">
                                  ✓ AI Insights Available
                                </span>
                              ) : (
                                <span className="user-modal__insights-tag user-modal__insights-tag--none">
                                  Analysis Ready
                                </span>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Footer: Stats & Actions (Delete + Open) */}
                        <div className="user-modal__history-footer">
                          {!isTabular ? (
                            <span className="user-modal__history-count">
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: "4px" }}>
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                              </svg>
                              {qCount} {qCount === 1 ? "question" : "questions"}
                            </span>
                          ) : (
                            <span className="user-modal__history-count">
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: "4px" }}>
                                <path d="M18 20V10M12 20V4M6 20v-6" />
                              </svg>
                              {item.has_insights ? "Full Analysis + Insights" : "Dataset Profile"}
                            </span>
                          )}

                          <div className="user-modal__actions-wrap">
                            {/* Delete Button with Confirmation */}
                            {isConfirming ? (
                              <div className="user-modal__confirm-box" role="alertdialog" aria-label="Confirm permanent deletion">
                                <span className="user-modal__confirm-text">Delete permanently?</span>
                                <button
                                  type="button"
                                  className="user-modal__confirm-btn user-modal__confirm-btn--delete"
                                  onClick={() => handleDelete(docId)}
                                  disabled={isThisDeleting}
                                >
                                  {isThisDeleting ? "Deleting..." : "Yes, Delete"}
                                </button>
                                <button
                                  type="button"
                                  className="user-modal__confirm-btn user-modal__confirm-btn--cancel"
                                  onClick={() => setConfirmDeleteId(null)}
                                  disabled={isThisDeleting}
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                type="button"
                                className="user-modal__delete-btn"
                                title="Delete this document and all associated data"
                                aria-label={`Delete ${docName}`}
                                onClick={() => setConfirmDeleteId(docId)}
                              >
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="3 6 5 6 21 6" />
                                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                  <line x1="10" y1="11" x2="10" y2="17" />
                                  <line x1="14" y1="11" x2="14" y2="17" />
                                </svg>
                                Delete
                              </button>
                            )}

                            {/* Open Action */}
                            <button
                              type="button"
                              className="user-modal__open-btn"
                              onClick={() => {
                                onClose();
                                onSelectDocument({
                                  id: docId,
                                  saved_filename: item.saved_filename,
                                  original_filename: docName,
                                  file_type: fileType,
                                  file_size_bytes: item.file_size_bytes,
                                });
                              }}
                            >
                              {!isTabular ? "Open Chat →" : "Open Analysis →"}
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
