import "./ResultsPlaceholder.css";

const UPCOMING_FEATURES = [
  { icon: "📊", label: "Data Overview", desc: "Summary statistics & schema" },
  { icon: "💡", label: "Auto Insights", desc: "AI-detected patterns & trends" },
  { icon: "📈", label: "Smart Charts",  desc: "3-4 relevant visualisations" },
  { icon: "💬", label: "AI Q&A",        desc: "Ask questions about your data" },
];

export default function ResultsPlaceholder() {
  return (
    <section className="results-placeholder" aria-label="Analysis results area">
      {/* Header */}
      <div className="results-placeholder__header">
        <h2 className="results-placeholder__title">Analysis Results</h2>
        <span className="results-placeholder__tag">Awaiting upload</span>
      </div>

      {/* 1. Four Feature Cards in 2x2 Grid */}
      <div className="results-placeholder__grid" role="list">
        {UPCOMING_FEATURES.map(({ icon, label, desc }) => (
          <div key={label} className="feature-card" role="listitem">
            <span className="feature-card__icon" aria-hidden="true">{icon}</span>
            <div className="feature-card__body">
              <p className="feature-card__label">{label}</p>
              <p className="feature-card__desc">{desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* 2. Two Lower Sections: Side-by-Side Equal Width */}
      <div className="results-placeholder__tracks">
        {/* Track 1: Automated Analytics */}
        <div className="placeholder-track">
          <div className="placeholder-track__header">
            <span className="placeholder-track__pill placeholder-track__pill--tabular">CSV & XLSX</span>
            <h3 className="placeholder-track__title">Automated Analytics</h3>
          </div>
          <ul className="placeholder-track__list">
            <li>
              <span className="placeholder-track__bullet">✓</span>
              <span><strong>Statistical Profiling:</strong> Mean, median, standard deviation, quantiles & category frequencies</span>
            </li>
            <li>
              <span className="placeholder-track__bullet">✓</span>
              <span><strong>Data Quality Checks:</strong> Missing cell counts, duplicate row detection, and schema types</span>
            </li>
            <li>
              <span className="placeholder-track__bullet">✓</span>
              <span><strong>Dynamic Visualizations:</strong> Variance-ranked bar charts, trend lines, and scatter plots</span>
            </li>
            <li>
              <span className="placeholder-track__bullet">✓</span>
              <span><strong>Groq AI Insights:</strong> Grounded executive narrative highlighting patterns, correlations & anomalies</span>
            </li>
          </ul>
        </div>

        {/* Track 2: Grounded Document RAG */}
        <div className="placeholder-track">
          <div className="placeholder-track__header">
            <span className="placeholder-track__pill placeholder-track__pill--doc">PDF & DOCX</span>
            <h3 className="placeholder-track__title">Grounded Document RAG</h3>
          </div>
          <ul className="placeholder-track__list">
            <li>
              <span className="placeholder-track__bullet">✓</span>
              <span><strong>Deep Text Extraction:</strong> Multi-page parsing preserving paragraph structure & tables</span>
            </li>
            <li>
              <span className="placeholder-track__bullet">✓</span>
              <span><strong>Semantic Vector Indexing:</strong> Overlapping chunk embeddings indexed in-memory</span>
            </li>
            <li>
              <span className="placeholder-track__bullet">✓</span>
              <span><strong>Document AI Chat:</strong> Ask broad summaries, key findings, or specific detailed questions</span>
            </li>
            <li>
              <span className="placeholder-track__bullet">✓</span>
              <span><strong>Verified Citations:</strong> Answers cite exact page and paragraph sources with expandable text</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
