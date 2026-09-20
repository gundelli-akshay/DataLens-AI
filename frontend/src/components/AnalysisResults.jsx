import "./AnalysisResults.css";
import ChartPanel from "./ChartPanel";

// ── Number formatting helpers ──────────────────────────────────
function fmt(n) {
  if (n === null || n === undefined) return "—";
  return typeof n === "number" ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : n;
}
function fmtPct(n) {
  if (n === null || n === undefined) return "—";
  return `${n.toFixed(1)}%`;
}

// ── Category badge ─────────────────────────────────────────────
function CategoryBadge({ category }) {
  return (
    <span className={`ar-badge ar-badge--${category}`} aria-label={`${category} column`}>
      {category}
    </span>
  );
}

// ── Overview stat cards ────────────────────────────────────────
function StatCard({ label, value, accent }) {
  return (
    <div className={`ar-stat${accent ? " ar-stat--accent" : ""}`}>
      <span className="ar-stat__value">{value}</span>
      <span className="ar-stat__label">{label}</span>
    </div>
  );
}

// ── Numeric stats mini-card ────────────────────────────────────
function NumericCard({ colName, stats }) {
  const items = [
    { label: "Mean",   value: fmt(stats.mean) },
    { label: "Median", value: fmt(stats.median) },
    { label: "Std",    value: fmt(stats.std) },
    { label: "Min",    value: fmt(stats.min) },
    { label: "Max",    value: fmt(stats.max) },
    { label: "Count",  value: fmt(stats.count) },
  ];
  return (
    <div className="ar-num-card">
      <h4 className="ar-num-card__name" title={colName}>{colName}</h4>
      <div className="ar-num-card__grid">
        {items.map(({ label, value }) => (
          <div key={label} className="ar-num-card__item">
            <span className="ar-num-card__item-label">{label}</span>
            <span className="ar-num-card__item-value">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Categorical top-values bar ─────────────────────────────────
function CategoricalCard({ colName, summary }) {
  const max = summary.top_values[0]?.count || 1;
  return (
    <div className="ar-cat-card">
      <div className="ar-cat-card__header">
        <span className="ar-cat-card__name" title={colName}>{colName}</span>
        <span className="ar-cat-card__unique">{fmt(summary.unique_count)} unique</span>
      </div>
      <div className="ar-cat-card__values">
        {summary.top_values.map(({ value, count }) => (
          <div key={value} className="ar-cat-card__row">
            <span className="ar-cat-card__val" title={value}>{value}</span>
            <div className="ar-cat-card__bar-wrap">
              <div
                className="ar-cat-card__bar"
                style={{ width: `${Math.round((count / max) * 100)}%` }}
                role="img"
                aria-label={`${count} occurrences`}
              />
            </div>
            <span className="ar-cat-card__count">{fmt(count)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────
export default function AnalysisResults({ data }) {
  if (!data) return null;

  const {
    filename, file_type, sheet_name,
    shape, columns,
    missing_total, duplicate_rows,
    numeric_summary, categorical_summary,
  } = data;

  const numericCols     = columns.filter((c) => c.category === "numeric");
  const categoricalCols = columns.filter((c) => c.category === "categorical");
  const dateCols        = columns.filter((c) => c.category === "date");

  const hasMissing = missing_total > 0;
  const hasDupes   = duplicate_rows > 0;

  return (
    <div className="ar" role="region" aria-label="Dataset analysis results">

      {/* ── Header ── */}
      <div className="ar-header">
        <div className="ar-header__left">
          <h2 className="ar-header__filename" title={filename}>{filename}</h2>
          <div className="ar-header__meta">
            <span className="ar-header__type">{file_type}</span>
            {sheet_name && (
              <span className="ar-header__sheet">Sheet: {sheet_name}</span>
            )}
          </div>
        </div>
        <div className="ar-header__badge">Analysis complete</div>
      </div>

      {/* ── Overview stats ── */}
      <div className="ar-section">
        <div className="ar-stats-grid">
          <StatCard label="Rows"            value={fmt(shape.rows)} />
          <StatCard label="Columns"         value={fmt(shape.columns)} />
          <StatCard label="Missing Values"  value={fmt(missing_total)} accent={hasMissing} />
          <StatCard label="Duplicate Rows"  value={fmt(duplicate_rows)} accent={hasDupes} />
        </div>
      </div>

      {/* ── Column overview table ── */}
      <div className="ar-section">
        <h3 className="ar-section__title">Column Overview</h3>
        <div className="ar-table-wrap" role="region" aria-label="Column overview table" tabIndex={0}>
          <table className="ar-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Column</th>
                <th>Type</th>
                <th>Category</th>
                <th>Missing</th>
                <th>Unique</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((col, i) => (
                <tr key={col.name}>
                  <td className="ar-table__idx">{i + 1}</td>
                  <td className="ar-table__name" title={col.name}>{col.name}</td>
                  <td className="ar-table__dtype">{col.dtype}</td>
                  <td><CategoryBadge category={col.category} /></td>
                  <td className={col.missing_count > 0 ? "ar-table__warn" : ""}>
                    {col.missing_count > 0
                      ? `${fmt(col.missing_count)} (${fmtPct(col.missing_pct)})`
                      : "—"}
                  </td>
                  <td>{fmt(col.unique_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Numeric statistics ── */}
      {Object.keys(numeric_summary).length > 0 && (
        <div className="ar-section">
          <h3 className="ar-section__title">
            Numeric Statistics
            <span className="ar-section__count">{numericCols.length} columns</span>
          </h3>
          <div className="ar-num-grid">
            {Object.entries(numeric_summary).map(([col, stats]) => (
              <NumericCard key={col} colName={col} stats={stats} />
            ))}
          </div>
        </div>
      )}

      {/* ── Categorical summary ── */}
      {Object.keys(categorical_summary).length > 0 && (
        <div className="ar-section">
          <h3 className="ar-section__title">
            Categorical Summary
            <span className="ar-section__count">{categoricalCols.length} columns</span>
          </h3>
          <div className="ar-cat-grid">
            {Object.entries(categorical_summary).map(([col, summary]) => (
              <CategoricalCard key={col} colName={col} summary={summary} />
            ))}
          </div>
        </div>
      )}

      {/* ── Date columns note ── */}
      {dateCols.length > 0 && (
        <div className="ar-section">
          <h3 className="ar-section__title">Date Columns</h3>
          <div className="ar-date-list">
            {dateCols.map((c) => (
              <span key={c.name} className="ar-date-item">{c.name}</span>
            ))}
          </div>
        </div>
      )}

      {/* ── Charts ── */}
      {data.chart_data?.length > 0 && (
        <div className="ar-section">
          <ChartPanel charts={data.chart_data} />
        </div>
      )}

    </div>
  );
}