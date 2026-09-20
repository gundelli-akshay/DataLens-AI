import { useState, useEffect, useRef } from "react";
import { chatDocument, indexDocument } from "../services/api";
import "./DocumentChat.css";

const SUGGESTIONS = [
  "Summarize the main points of this document.",
  "What key topics or findings are discussed?",
  "What are the major conclusions or recommendations?",
];

export default function DocumentChat({ document }) {
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
        content: response.answer || "No response received.",
        sources: response.sources || [],
        model: response.model,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setErrorMsg(err.message || "Failed to retrieve an answer. Please try again.");
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
        id: `init_${Date.now()}`,
        role: "assistant",
        content: `Conversation reset. What else would you like to know about **${fileName}**?`,
        sources: [],
      },
    ]);
    setErrorMsg("");
  }

  return (
    <div className="doc-chat" aria-label="Document AI Chat">
      {/* Header */}
      <div className="doc-chat__header">
        <div className="doc-chat__file-info">
          <span className={`doc-chat__badge doc-chat__badge--${fileType.toLowerCase()}`}>
            {fileType}
          </span>
          <div>
            <h3 className="doc-chat__filename">{fileName}</h3>
            <span className="doc-chat__status">
              <span className="doc-chat__status-dot" />
              Grounded AI Q&amp;A Active
            </span>
          </div>
        </div>
        <button
          type="button"
          className="doc-chat__reset-btn"
          onClick={handleReset}
          title="Clear chat history"
        >
          Clear Chat
        </button>
      </div>

      {/* Suggested prompts if only 1 message */}
      {messages.length === 1 && (
        <div className="doc-chat__suggestions">
          <span className="doc-chat__suggestions-label">Suggested Questions:</span>
          <div className="doc-chat__chips">
            {SUGGESTIONS.map((sugg, i) => (
              <button
                key={i}
                type="button"
                className="doc-chat__chip"
                onClick={() => handleSend(sugg)}
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
              {msg.role === "assistant" ? "🤖" : "👤"}
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
                            📍 {src.source}
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
            <div className="doc-chat__msg-avatar">🤖</div>
            <div className="doc-chat__msg-content">
              <div className="doc-chat__thinking">
                <span className="doc-chat__dot" />
                <span className="doc-chat__dot" />
                <span className="doc-chat__dot" />
                <span className="doc-chat__thinking-text">Searching document context...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error banner */}
      {errorMsg && (
        <div className="doc-chat__error" role="alert">
          <span className="doc-chat__error-icon">⚠️</span>
          <div className="doc-chat__error-msg">{errorMsg}</div>
        </div>
      )}

      {/* Input bar */}
      <form
        className="doc-chat__form"
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
      >
        <input
          ref={inputRef}
          type="text"
          className="doc-chat__input"
          placeholder={`Ask about ${fileName}...`}
          value={inputQuery}
          onChange={(e) => setInputQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
        />
        <button
          type="submit"
          className="doc-chat__send-btn"
          disabled={!inputQuery.trim() || isLoading}
        >
          Send
        </button>
      </form>
    </div>
  );
}
