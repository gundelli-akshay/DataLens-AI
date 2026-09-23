import MarkdownRenderer from "./MarkdownRenderer";
import { useState, useEffect } from "react";
import { getAiInsights } from "../services/api";
import "./AiInsightsSection.css";

export default function AiInsightsSection({ analysisData, savedFilename }) {
  const [status, setStatus] = useState(analysisData?.ai_insights ? "success" : "idle"); // idle | loading | success | error
  const [insights, setInsights] = useState(analysisData?.ai_insights || "");
  const [modelLabel, setModelLabel] = useState(
    analysisData?.is_fallback ? "Model: Groq · Fallback" : "Model: Gemini"
  );

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
      if (res.is_fallback || (res.model && res.model.toLowerCase().includes("fallback"))) {
        setModelLabel("Model: Groq · Fallback");
      } else if (res.model && res.model.toLowerCase().includes("groq")) {
        setModelLabel("Model: Groq");
      } else {
        setModelLabel("Model: Gemini");
      }
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
          <h3 className="ai-insights__title">Automated Insights</h3>
          <span className="ai-insights__badge">DATA POWERED</span>
          <span className="ai-insights__model-info">{modelLabel}</span>
        </div>

        {status === "success" && (
          <div className="ai-insights__actions">
            <button
              type="button"
              className="ai-insights__copy-btn"
              onClick={handleCopy}
              aria-label="Copy insights to clipboard"
            >
              {copied ? "Copied" : "Copy"}
            </button>
            <button
              type="button"
              className="ai-insights__regen-btn"
              onClick={handleGenerateInsights}
              aria-label="Regenerate AI Insights"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "4px" }}>
                <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
                <polyline points="21 3 21 8 16 8" />
                <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
                <polyline points="8 16 3 16 3 21" />
              </svg>
              Regenerate
            </button>
          </div>
        )}
      </div>

      {status === "idle" && (
        <div className="ai-insights__idle">
          <p className="ai-insights__desc">
            Synthesize key patterns, correlation signals, category skews, and data anomalies from the computed statistics.
          </p>
          <button
            type="button"
            className="ai-insights__btn"
            onClick={handleGenerateInsights}
          >
            Generate Narrative Insights
          </button>
        </div>
      )}

      {status === "loading" && (
        <div className="ai-insights__loading" role="status" aria-live="polite">
          <div className="ai-insights__spinner" aria-hidden="true" />
          <span className="ai-insights__loading-text">
            Synthesizing statistical distributions and generating narrative report...
          </span>
        </div>
      )}

      {status === "error" && (
        <div className="ai-insights__error" role="alert">
          <div>
            <p className="ai-insights__error-title">Failed to generate insights</p>
            <p className="ai-insights__error-msg">{errorMsg}</p>
            <button
              type="button"
              className="ai-insights__retry-btn"
              onClick={handleGenerateInsights}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {status === "success" && (
        <div className="ai-insights__body">
          <MarkdownRenderer content={insights} />
        </div>
      )}
    </div>
  );
}
