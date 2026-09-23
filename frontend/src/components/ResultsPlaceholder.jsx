import "./ResultsPlaceholder.css";

export default function ResultsPlaceholder() {
  return (
    <section className="workspace-overview" aria-label="Analytical capabilities overview">
      <div className="workspace-overview__header">
        <div>
          <h2 className="workspace-overview__title">Workspace Capabilities</h2>
          <p className="workspace-overview__subtitle">
            Outputs generated automatically when a spreadsheet or reference document is loaded.
          </p>
        </div>
        <span className="workspace-overview__status">Awaiting Upload</span>
      </div>

      <div className="workspace-overview__grid">
        {/* Capability 1: Spreadsheet Analysis */}
        <div className="capability-card">
          <div className="capability-card__header">
            <div className="capability-card__icon" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            </div>
            <div>
              <h3 className="capability-card__title">Spreadsheet Analytics</h3>
              <p className="capability-card__meta">Statistical summaries and charts</p>
            </div>
          </div>

          <ul className="capability-card__list">
            <li>
              <span className="capability-card__bullet" aria-hidden="true">&bull;</span>
              <span><strong>Data profiling:</strong> Dimension shapes, inferred column types, missing cell counts, and duplicate row detection.</span>
            </li>
            <li>
              <span className="capability-card__bullet" aria-hidden="true">&bull;</span>
              <span><strong>Distribution metrics:</strong> Mean, median, standard deviation, minimum, maximum, and quantiles for numeric metrics.</span>
            </li>
            <li>
              <span className="capability-card__bullet" aria-hidden="true">&bull;</span>
              <span><strong>Visual charts:</strong> Variance-ranked bar charts, trend lines, histograms, and scatter plots generated from column distributions.</span>
            </li>
            <li>
              <span className="capability-card__bullet" aria-hidden="true">&bull;</span>
              <span><strong>Executive narrative:</strong> Structured summary synthesizing distribution skews, primary patterns, and anomalies.</span>
            </li>
          </ul>
        </div>

        {/* Capability 2: Document Q&A */}
        <div className="capability-card">
          <div className="capability-card__header">
            <div className="capability-card__icon" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            </div>
            <div>
              <h3 className="capability-card__title">Document Search &amp; Q&amp;A</h3>
              <p className="capability-card__meta">Grounded answers with citations</p>
            </div>
          </div>

          <ul className="capability-card__list">
            <li>
              <span className="capability-card__bullet" aria-hidden="true">&bull;</span>
              <span><strong>Structure extraction:</strong> Multi-page text parsing that preserves section headings, paragraph boundaries, and tables.</span>
            </li>
            <li>
              <span className="capability-card__bullet" aria-hidden="true">&bull;</span>
              <span><strong>In-memory vector retrieval:</strong> Overlapping semantic chunks indexed for fast similarity matching against your specific questions.</span>
            </li>
            <li>
              <span className="capability-card__bullet" aria-hidden="true">&bull;</span>
              <span><strong>Contextual answers:</strong> Formulates direct responses strictly anchored to extracted document context with zero speculation.</span>
            </li>
            <li>
              <span className="capability-card__bullet" aria-hidden="true">&bull;</span>
              <span><strong>Verified citations:</strong> Every response references exact page numbers and paragraph sources with expandable excerpts.</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
