import { useState, useEffect, useRef } from "react";
import { chatDocument, indexDocument } from "../services/api";
import "./DocumentChat.css";

const SUGGESTIONS = [
  "Summarize the main points of this document.",
  "What key topics or findings are discussed?",
  "What are the major conclusions or recommendations?",
];

export default function DocumentChat({ document, user, onRequireAuth }) {
  const fileName = document?.original_filename || document?.saved_filename || "Document";
  const fileType = document?.file_type || "PDF";
  const savedFilename = document?.saved_filename;

  const [messages, setMessages] = useState([
    {
      id: "init",
      role: "assistant",
      content: `I've analyzed **${fileName}** (${fileType}). Ask any question about this document — every answer is strictly grounded in the document context with verified source citations.`,
      sources: [],
    },
  ]);
  const [inputQuery, setInputQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [expandedSources, setExpandedSources] = useState({});

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll messages to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Index document in background upon mount/upload if not already done
  useEffect(() => {
    if (savedFilename) {
      indexDocument(savedFilename).catch(() => {
        // Chat endpoint handles auto-indexing fallback if this fails
      });
    }
  }, [savedFilename]);

  function toggleSourceSnippet(msgId, sourceIdx) {
    const key = `${msgId}_${sourceIdx}`;
    setExpandedSources((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleSend(queryToSend) {
    const question = (queryToSend || inputQuery).trim();
    if (!question || isLoading) return;

    if (!user && onRequireAuth) {
      setErrorMsg("Please sign in to chat with documents.");
      onRequireAuth();
      return;
    }

    setErrorMsg("");
    setInputQuery("");

    const userMsgId = `user_${Date.now()}`;
    const userMsg = {
      id: userMsgId,
      role: "user",
      content: question,
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await chatDocument({
        question,
        filename: fileName,
        savedFilename: savedFilename,
      });

      const assistantMsg = {
        id: `asst_${Date.now()}`,
        role: "assistant",
        content: response.answer || "The provided document does not contain sufficient information to answer this question.",
        sources: response.sources || [],
        model: response.model,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const msg = err.message || "";
      if (msg.includes("credentials") || msg.includes("authenticated") || msg.includes("401")) {
        setErrorMsg("Please sign in to chat with documents.");
        if (onRequireAuth) onRequireAuth();
      } else {
        setErrorMsg(msg || "Failed to retrieve an answer. Please try again.");
      }
    } finally {
      setIsLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleReset() {
    setMessages([
      {
        id: `reset_${Date.now()}`,
        role: "assistant",
        content: `Conversation reset. What else would you like to know about **${fileName}**?`,
        sources: [],
      },
    ]);
    setErrorMsg("");
  }

  return (
    <div className="doc-chat" role="region" aria-label="Document AI Chat">
      {/* Header */}
      <div className="doc-chat__header">
        <div className="doc-chat__title-wrap">
          <div className="doc-chat__icon-badge" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          </div>
          <div>
            <h3 className="doc-chat__title">Document AI Chat</h3>
            <span className="doc-chat__subtitle">
              {fileName} &bull; {fileType}
            </span>
          </div>
        </div>

        <div className="doc-chat__controls">
          <button
            type="button"
            className="doc-chat__reset-btn"
            onClick={handleReset}
            title="Reset conversation"
            aria-label="Reset conversation"
          >
            Clear Chat
          </button>
        </div>
      </div>

      {/* Suggested Questions */}
      {messages.length <= 1 && (
        <div className="doc-chat__suggestions">
          <span className="doc-chat__suggestions-label">Suggested prompts:</span>
          <div className="doc-chat__suggestions-pills">
            {SUGGESTIONS.map((sugg, idx) => (
              <button
                key={idx}
                type="button"
                className="doc-chat__pill"
                onClick={() => handleSend(sugg)}
                disabled={isLoading}
              >
                {sugg}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Chat Messages List */}
      <div className="doc-chat__messages" role="log" aria-live="polite">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`doc-chat__msg doc-chat__msg--${msg.role}`}
          >
            <div className="doc-chat__msg-avatar">
              {msg.role === "assistant" ? (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                </svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              )}
            </div>
            <div className="doc-chat__msg-content">
              <p className="doc-chat__msg-text">{msg.content}</p>

              {/* Source citations */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="doc-chat__sources">
                  <span className="doc-chat__sources-title">Verified Sources:</span>
                  <div className="doc-chat__sources-list">
                    {msg.sources.map((src, sIdx) => {
                      const isExpanded = expandedSources[`${msg.id}_${sIdx}`];
                      return (
                        <div key={sIdx} className="doc-chat__source-item">
                          <button
                            type="button"
                            className="doc-chat__source-tag"
                            onClick={() => toggleSourceSnippet(msg.id, sIdx)}
                            title="Click to view cited excerpt"
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "3px" }}>
                              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                              <polyline points="14 2 14 8 20 8" />
                            </svg>
                            {src.source}
                            <span className="doc-chat__source-arrow">
                              {isExpanded ? "▲" : "▼"}
                            </span>
                          </button>
                          {isExpanded && src.snippet && (
                            <div className="doc-chat__source-snippet">
                              "{src.snippet}"
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Thinking Indicator */}
        {isLoading && (
          <div className="doc-chat__msg doc-chat__msg--assistant">
            <div className="doc-chat__msg-avatar">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
            </div>
            <div className="doc-chat__msg-content">
              <div className="doc-chat__thinking">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error display */}
      {errorMsg && (
        <div className="doc-chat__error" role="alert">
          <span className="doc-chat__error-icon">!</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Input Box */}
      <form
        className="doc-chat__input-bar"
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
      >
        <input
          ref={inputRef}
          type="text"
          className="doc-chat__input"
          placeholder={`Ask anything grounded in ${fileName}...`}
          value={inputQuery}
          onChange={(e) => setInputQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          aria-label="Ask a question about the document"
        />
        <button
          type="submit"
          className="doc-chat__send-btn"
          disabled={isLoading || !inputQuery.trim()}
          aria-label="Send question"
        >
          {isLoading ? (
            <span className="doc-chat__btn-spinner" />
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          )}
        </button>
      </form>
    </div>
  );
}
