import MarkdownRenderer from "./MarkdownRenderer";
import { useState, useEffect } from "react";
import { getAiInsights } from "../services/api";
import "./AiInsightsSection.css";

export default function AiInsightsSection({ analysisData, savedFilename }) {
  const [status, setStatus] = useState(analysisData?.ai_insights ? "success" : "idle"); // idle | loading | success | error
  const [insights, setInsights] = useState(analysisData?.ai_insights || "");

  useEffect(() => {
    if (analysisData?.ai_insights) {
      setInsights(analysisData.ai_insights);
      setStatus("success");
    } else {
      setInsights("");
      setStatus("idle");
    }
  }, [analysisData]);
  const [errorMsg, setErrorMsg] = useState("");
  const [copied, setCopied] = useState(false);

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
      setErrorMsg(err.message || "Failed to generate AI insights. Please try again.");
    }
  }

  function handleCopy() {
    if (!insights) return;
    navigator.clipboard.writeText(insights).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="ai-insights" role="region" aria-label="AI Insights">
      <div className="ai-insights__header">
        <div className="ai-insights__title-wrap">
          <span className="ai-insights__icon" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
          </span>
          <h3 className="ai-insights__title">AI Insights</h3>
          <span className="ai-insights__badge">Grounded Analysis</span>
        </div>

        {status === "success" && (
          <div className="ai-insights__actions">
            <button
              className="ai-insights__copy-btn"
              onClick={handleCopy}
              aria-label="Copy insights to clipboard"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
            <button
              className="ai-insights__regen-btn"
              onClick={handleGenerateInsights}
              aria-label="Regenerate AI Insights"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "4px" }}>
                <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
                <path d="M21 3v5h-5" />
                <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
                <path d="M3 21v-5h5" />
              </svg>
              Regenerate
            </button>
          </div>
        )}
      </div>

      {status === "idle" && (
        <div className="ai-insights__idle">
          <p className="ai-insights__desc">
            Use AI to explain grounded patterns, summarize distributions, and highlight data quality findings from this dataset.
          </p>
          <button
            className="ai-insights__btn"
            onClick={handleGenerateInsights}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "6px" }}>
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
            Generate AI Insights
          </button>
        </div>
      )}

      {status === "loading" && (
        <div className="ai-insights__loading" role="status" aria-live="polite">
          <div className="ai-insights__spinner" aria-hidden="true" />
          <p className="ai-insights__loading-text">
            Synthesizing calculated statistics and generating grounded insights...
          </p>
        </div>
      )}

      {status === "error" && (
        <div className="ai-insights__error" role="alert">
          <div className="ai-insights__error-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
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
          <MarkdownRenderer content={insights} />
        </div>
      )}
    </div>
  );
}