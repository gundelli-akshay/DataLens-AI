import "./ResultsPlaceholder.css";

const UPCOMING_FEATURES = [
  { icon: "📊", label: "Data Overview",      desc: "Summary statistics & schema" },
  { icon: "💡", label: "Auto Insights",      desc: "AI-detected patterns & trends" },
  { icon: "📈", label: "Smart Charts",       desc: "2–3 relevant visualisations" },
  { icon: "🤖", label: "AI Q&A",             desc: "Ask questions about your data" },
];

export default function ResultsPlaceholder() {
  return (
    <section className="results-placeholder" aria-label="Analysis results area">
      <div className="results-placeholder__header">
        <h2 className="results-placeholder__title">Analysis Results</h2>
        <span className="results-placeholder__tag">Awaiting upload</span>
      </div>

      <div className="results-placeholder__grid" role="list">
        {UPCOMING_FEATURES.map(({ icon, label, desc }) => (
          <div key={label} className="feature-card" role="listitem">
            <span className="feature-card__icon" aria-hidden="true">{icon}</span>
            <div>
              <p className="feature-card__label">{label}</p>
              <p className="feature-card__desc">{desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
