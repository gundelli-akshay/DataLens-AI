import { useState, useEffect } from "react";
import { getUserHistory, deleteDocument } from "../services/api";
import DeleteConfirmModal from "./DeleteConfirmModal";
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
  onDeleteDocument,
  onSignOut,
}) {
  const [activeTab, setActiveTab] = useState(initialTab === "documents" ? "history" : initialTab);
  const [historyList, setHistoryList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab === "documents" ? "history" : initialTab);
      setError("");
      setDeleteTarget(null);
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

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  async function handleConfirmDelete() {
    if (!deleteTarget) return;
    const docId = deleteTarget.id || deleteTarget.document_id || deleteTarget.saved_filename;
    try {
      await deleteDocument(docId);
      setHistoryList((prev) =>
        prev.filter((item) => (item.id || item.document_id || item.saved_filename) !== docId)
      );
      if (onDeleteDocument) {
        onDeleteDocument(deleteTarget);
      }
      setDeleteTarget(null);
    } catch (err) {
      setError(err.message || "Failed to delete item. Please try again.");
      setDeleteTarget(null);
    }
  }

  if (!isOpen) return null;

  const displayName = user?.full_name || user?.email || "User";
  const initial = displayName.charAt(0).toUpperCase();

  return (
    <div className="user-modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="user-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header & Navigation */}
        <div className="user-modal__header">
          <div className="user-modal__nav">
            <button
              type="button"
              className={`user-modal__tab ${activeTab === "profile" ? "active" : ""}`}
              onClick={() => setActiveTab("profile")}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              Account
            </button>
            <button
              type="button"
              className={`user-modal__tab ${activeTab === "history" ? "active" : ""}`}
              onClick={() => setActiveTab("history")}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              History &amp; Files
            </button>
          </div>
          <button
            type="button"
            className="user-modal__close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            &times;
          </button>
        </div>

        {/* Modal Body */}
        <div className="user-modal__body">
          {error && <div className="user-modal__error" role="alert">{error}</div>}

          {/* TAB 1: Profile */}
          {activeTab === "profile" && (
            <div className="user-modal__profile">
              <div className="user-modal__profile-card">
                <div className="user-modal__avatar">{initial}</div>
                <div className="user-modal__profile-info">
                  <h3 className="user-modal__profile-name">{displayName}</h3>
                  <p className="user-modal__profile-email">{user?.email}</p>
                </div>
              </div>

              <div className="user-modal__details-grid">
                <div className="user-modal__detail-item">
                  <span className="user-modal__detail-label">Authentication Provider</span>
                  <span className="user-modal__detail-val">
                    {user?.auth_provider === "google" ? "Google Identity" : "Email & Password"}
                  </span>
                </div>
                <div className="user-modal__detail-item">
                  <span className="user-modal__detail-label">Account Status</span>
                  <span className="user-modal__detail-val user-modal__detail-val--active">Active</span>
                </div>
              </div>

              <div className="user-modal__profile-actions">
                <button
                  type="button"
                  className="user-modal__signout-btn"
                  onClick={() => {
                    onClose();
                    onSignOut?.();
                  }}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                  Sign Out
                </button>
              </div>
            </div>
          )}

          {/* TAB 2: History & Files */}
          {activeTab === "history" && (
            <div className="user-modal__history">
              {loading ? (
                <div className="user-modal__loading">
                  <div className="user-modal__spinner" />
                  <span>Loading history...</span>
                </div>
              ) : historyList.length === 0 ? (
                <div className="user-modal__empty">
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                  <p className="user-modal__empty-title">No files or chats yet</p>
                  <p className="user-modal__empty-desc">
                    Upload a dataset to run automated statistical analysis, or upload a document to ask grounded questions.
                  </p>
                </div>
              ) : (
                <div className="user-modal__history-list">
                  {historyList.map((item) => {
                    const docId = item.id || item.saved_filename;
                    const fileType = (item.file_type || "PDF").toUpperCase();
                    const docName = item.original_filename || item.saved_filename || "Document";
                    const isTabular = ["CSV", "XLSX"].includes(fileType);
                    const qCount = item.chat_count || item.total_messages || 0;

                    return (
                      <div key={docId} className="user-modal__history-item">
                        {/* Header: File Name & Type */}
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

                        {/* Content Area */}
                        {!isTabular ? (
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
                                Document indexed and ready for grounded Q&amp;A. No questions asked yet.
                              </p>
                            )}
                          </div>
                        ) : (
                          <div className="user-modal__history-content">
                            <div className="user-modal__tabular-meta">
                              <span className="user-modal__tabular-size">
                                {formatBytes(item.file_size_bytes)}
                              </span>
                              <span className="user-modal__tabular-dot">&middot;</span>
                              <span className="user-modal__tabular-uploaded">
                                Uploaded {formatDate(item.uploaded_at)}
                              </span>
                              <span className="user-modal__tabular-dot">&middot;</span>
                              {item.has_insights ? (
                                <span className="user-modal__insights-tag user-modal__insights-tag--ready">
                                  Insights Available
                                </span>
                              ) : (
                                <span className="user-modal__insights-tag user-modal__insights-tag--none">
                                  Analysis Ready
                                </span>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Footer: Stats & Actions */}
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
                            {/* Delete Button triggering DeleteConfirmModal */}
                            <button
                              type="button"
                              className="user-modal__delete-btn"
                              title="Delete this document and all associated data"
                              aria-label={`Delete ${docName}`}
                              onClick={() => setDeleteTarget(item)}
                            >
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="3 6 5 6 21 6" />
                                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                  <line x1="10" y1="11" x2="10" y2="17" />
                                  <line x1="14" y1="11" x2="14" y2="17" />
                              </svg>
                              Delete
                            </button>

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

      {/* Delete Confirmation Modal matching SignOutModal */}
      <DeleteConfirmModal
        isOpen={Boolean(deleteTarget)}
        title={
          deleteTarget?.action === "open_chat" || deleteTarget?.has_chat
            ? "Delete this conversation?"
            : deleteTarget?.action === "open_analysis" || deleteTarget?.has_analysis
            ? "Delete this analysis?"
            : "Delete this file?"
        }
        description={
          deleteTarget?.action === "open_chat" || deleteTarget?.has_chat
            ? "This conversation will be permanently removed."
            : deleteTarget?.action === "open_analysis" || deleteTarget?.has_analysis
            ? "This analysis will be permanently removed."
            : "This will permanently remove the file and its associated analysis."
        }
        itemName={deleteTarget?.original_filename || deleteTarget?.saved_filename || deleteTarget?.filename || deleteTarget?.document_name}
        confirmLabel="Delete"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}
