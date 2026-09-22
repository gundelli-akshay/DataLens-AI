import { useEffect, useRef, useState } from "react";
import "./SignOutModal.css";

export default function SignOutModal({ isOpen, onClose, onConfirm }) {
  const [isProcessing, setIsProcessing] = useState(false);
  const cancelBtnRef = useRef(null);

  // Focus cancel button on mount for safety & keyboard accessibility
  useEffect(() => {
    if (isOpen) {
      setIsProcessing(false);
      const timer = setTimeout(() => {
        cancelBtnRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Handle ESC key to close modal
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e) {
      if (e.key === "Escape" && !isProcessing) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, isProcessing]);

  if (!isOpen) return null;

  async function handleSignOutClick() {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      await onConfirm();
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <div
      className="signout-modal-overlay"
      onClick={isProcessing ? undefined : onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="signout-modal-title"
      aria-describedby="signout-modal-desc"
    >
      <div className="signout-modal-card" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="signout-modal-close"
          onClick={onClose}
          disabled={isProcessing}
          aria-label="Close sign out confirmation"
        >
          &times;
        </button>

        <div className="signout-modal-header">
          <div className="signout-modal-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </div>
          <h2 id="signout-modal-title" className="signout-modal-title">Sign out?</h2>
        </div>

        <p id="signout-modal-desc" className="signout-modal-desc">
          Are you sure you want to sign out?
        </p>

        <div className="signout-modal-actions">
          <button
            ref={cancelBtnRef}
            type="button"
            className="signout-btn signout-btn--cancel"
            onClick={onClose}
            disabled={isProcessing}
          >
            Cancel
          </button>
          <button
            type="button"
            className="signout-btn signout-btn--danger"
            onClick={handleSignOutClick}
            disabled={isProcessing}
          >
            {isProcessing ? "Signing out..." : "Sign Out"}
          </button>
        </div>
      </div>
    </div>
  );
}
