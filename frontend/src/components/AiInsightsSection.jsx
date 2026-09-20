import { useState } from "react";
import { getAiInsights } from "../services/api";
import "./AiInsightsSection.css";

/**
 * Simple markdown-like renderer for AI insights text.
 * Converts headers (###), bullet points (* or -), and bold (**text**) cleanly.
 */
function FormattedInsights({ text }) {
  if (!text) return null;

  const lines = text.split("\n");
  const elements = [];
  let currentList = [];

  function flushList() {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="ai-insights__list">
          {currentList.map((item, idx) => (
            <li key={idx} className="ai-insights__list-item">
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
      currentList = [];
    }
  }

  function renderInline(str) {
    // Basic bold parser: **word** -> <strong>word</strong>
    const parts = str.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }

    if (trimmed.startsWith("### ")) {
      flushList();
      elements.push(
        <h4 key={`h-${index}`} className="ai-insights__heading">
          {trimmed.replace(/^###\s*/, "")}
        </h4>
      );
    } else if (trimmed.startsWith("## ")) {
      flushList();
      elements.push(
        <h3 key={`h-${index}`} className="ai-insights__heading-large">
          {trimmed.replace(/^##\s*/, "")}
        </h3>
      );
    } else if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
      currentList.push(trimmed.replace(/^[*\-]\s*/, ""));
    } else {
      flushList();
      elements.push(
        <p key={`p-${index}`} className="ai-insights__paragraph">
          {renderInline(trimmed)}
        </p>
      );
    }
  });

  flushList();
  return <div className="ai-insights__body">{elements}</div>;
}

export default function AiInsightsSection({ analysisData, savedFilename }) {
  const [status, setStatus] = useState("idle"); // idle | loading | success | error
  const [insights, setInsights] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleGenerateInsights() {
    setStatus("loading");
    setErrorMsg("");

    try {
      const res = await getAiInsights({
        analysis: analysisData,
        savedFilename: savedFilename,
      });
      setInsights(res.insights || "No insights returned.");
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setErrorMsg(err.message || "Failed to generate AI insights.");
    }
  }

  return (
    <div className="ai-insights" role="region" aria-label="AI Insights">
      <div className="ai-insights__header">
        <div className="ai-insights__title-wrap">
          <span className="ai-insights__icon" aria-hidden="true">✨</span>
          <h3 className="ai-insights__title">AI Insights</h3>
          <span className="ai-insights__badge">LLM Powered</span>
        </div>

        {status === "success" && (
          <button
            className="ai-insights__regen-btn"
            onClick={handleGenerateInsights}
            aria-label="Regenerate AI Insights"
          >
            ↺ Regenerate
          </button>
        )}
      </div>

      {status === "idle" && (
        <div className="ai-insights__idle">
          <p className="ai-insights__desc">
            Use AI to explain patterns, summarize distributions, and highlight data quality findings from this dataset.
          </p>
          <button
            className="ai-insights__btn"
            onClick={handleGenerateInsights}
          >
            ✨ Generate AI Insights
          </button>
        </div>
      )}

      {status === "loading" && (
        <div className="ai-insights__loading" role="status" aria-live="polite">
          <div className="ai-insights__spinner" aria-hidden="true" />
          <p className="ai-insights__loading-text">
            Analyzing findings and generating AI insights...
          </p>
        </div>
      )}

      {status === "error" && (
        <div className="ai-insights__error" role="alert">
          <div className="ai-insights__error-icon" aria-hidden="true">⚠️</div>
          <div className="ai-insights__error-content">
            <p className="ai-insights__error-title">Unable to generate AI insights</p>
            <p className="ai-insights__error-msg">{errorMsg}</p>
            <button
              className="ai-insights__retry-btn"
              onClick={handleGenerateInsights}
            >
              Try Again
            </button>
          </div>
        </div>
      )}

      {status === "success" && (
        <div className="ai-insights__result">
          <FormattedInsights text={insights} />
        </div>
      )}
    </div>
  );
}