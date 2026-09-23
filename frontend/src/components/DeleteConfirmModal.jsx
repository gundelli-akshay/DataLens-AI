import { useEffect, useRef, useState } from "react";
import "./DeleteConfirmModal.css";

export default function DeleteConfirmModal({
  isOpen,
  title = "Delete this file?",
  description = "This will permanently remove the file and its associated analysis.",
  itemName,
  confirmLabel = "Delete",
  onClose,
  onConfirm,
}) {
  const [isProcessing, setIsProcessing] = useState(false);
  const cancelBtnRef = useRef(null);

  // Auto-focus cancel button on mount for safety and keyboard accessibility
  useEffect(() => {
    if (isOpen) {
      setIsProcessing(false);
      const timer = setTimeout(() => {
        cancelBtnRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Handle ESC key to safely dismiss modal
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

  async function handleDeleteClick() {
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
      className="delete-modal-overlay"
      onClick={isProcessing ? undefined : onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-modal-title"
      aria-describedby="delete-modal-desc"
    >
      <div className="delete-modal-card" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="delete-modal-close"
          onClick={onClose}
          disabled={isProcessing}
          aria-label="Close delete confirmation"
        >
          &times;
        </button>

        <div className="delete-modal-header">
          <div className="delete-modal-icon" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              width="24"
              height="24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
          </div>
          <h2 id="delete-modal-title" className="delete-modal-title">
            {title}
          </h2>
        </div>

        {itemName && (
          <p className="delete-modal-item" title={itemName}>
            {itemName}
          </p>
        )}

        <p id="delete-modal-desc" className="delete-modal-desc">
          {description}
        </p>

        <div className="delete-modal-actions">
          <button
            ref={cancelBtnRef}
            type="button"
            className="delete-btn delete-btn--cancel"
            onClick={onClose}
            disabled={isProcessing}
          >
            Cancel
          </button>
          <button
            type="button"
            className="delete-btn delete-btn--danger"
            onClick={handleDeleteClick}
            disabled={isProcessing}
          >
            {isProcessing ? "Deleting..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
