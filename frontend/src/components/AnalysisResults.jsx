import { useState } from "react";
import "./AnalysisResults.css";
import ChartPanel from "./ChartPanel";
import AiInsightsSection from "./AiInsightsSection";

// ── Number formatting helpers ──
function fmt(n) {
  if (n === null || n === undefined) return "—";
  return typeof n === "number" ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : n;
}
function fmtPct(n) {
  if (n === null || n === undefined) return "—";
  return `${n.toFixed(1)}%`;
}

// ── Category badge ──
function CategoryBadge({ category }) {
  return (
    <span className={`ar-badge ar-badge--${category}`} aria-label={`${category} column`}>
      {category}
    </span>
  );
}

// ── Overview stat cards ──
function StatCard({ label, value, accent }) {
  return (
    <div className={`ar-stat${accent ? " ar-stat--accent" : ""}`}>
      <span className="ar-stat__value">{value}</span>
      <span className="ar-stat__label">{label}</span>
    </div>
  );
}

// ── Numeric stats mini-card ──
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

// ── Categorical top-values bar ──
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

// ── Main component ──
export default function AnalysisResults({ data, savedFilename }) {
  if (!data) return null;

  const {
    filename, file_type, sheet_name,
    shape, columns,
    missing_total, duplicate_rows,
    numeric_summary, categorical_summary,
  } = data;

  // Expansion & Compact UI State
  const [colsExpanded, setColsExpanded] = useState(false);
  const [colsCollapsed, setColsCollapsed] = useState(false);

  const [numericMode, setNumericMode] = useState("table"); // "table" | "cards"
  const [numericExpanded, setNumericExpanded] = useState(false);
  const [numericCollapsed, setNumericCollapsed] = useState(false);

  const [catExpanded, setCatExpanded] = useState(false);
  const [catCollapsed, setCatCollapsed] = useState(false);

  const numericCols     = columns.filter((c) => c.category === "numeric");
  const categoricalCols = columns.filter((c) => c.category === "categorical");
  const dateCols        = columns.filter((c) => c.category === "date");

  const hasMissing = missing_total > 0;
  const hasDupes   = duplicate_rows > 0;

  // Limits for compact views
  const COL_COMPACT_LIMIT = 6;
  const NUM_COMPACT_LIMIT = 4;
  const CAT_COMPACT_LIMIT = 3;

  const visibleColumns = colsExpanded ? columns : columns.slice(0, COL_COMPACT_LIMIT);
  const numericEntries = Object.entries(numeric_summary);
  const visibleNumericEntries = numericExpanded ? numericEntries : numericEntries.slice(0, NUM_COMPACT_LIMIT);

  const catEntries = Object.entries(categorical_summary);
  const visibleCatEntries = catExpanded ? catEntries : catEntries.slice(0, CAT_COMPACT_LIMIT);

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

      {/* ── Overview stats: Balanced 6-card grid with exact dataset metrics ── */}
      <div className="ar-section">
        <div className="ar-stats-grid">
          <StatCard label="Rows"               value={fmt(shape.rows)} />
          <StatCard label="Columns"            value={fmt(shape.columns)} />
          <StatCard label="Numeric Columns"    value={fmt(numericCols.length)} />
          <StatCard label="Categorical Columns" value={fmt(categoricalCols.length)} />
          <StatCard label="Missing Values"     value={fmt(missing_total)} accent={hasMissing} />
          <StatCard label="Duplicate Rows"     value={fmt(duplicate_rows)} accent={hasDupes} />
        </div>
      </div>

      {/* ── AI Insights ── */}
      <div className="ar-section">
        <AiInsightsSection analysisData={data} savedFilename={savedFilename} />
      </div>

      {/* ── Column overview table (Compact & Expandable) ── */}
      <div className="ar-section">
        <div className="ar-section__header-bar">
          <h3 className="ar-section__title">
            Column Overview
            <span className="ar-section__count">{columns.length} columns</span>
          </h3>
          <div className="ar-section__controls">
            <button
              type="button"
              className="ar-toggle-btn"
              onClick={() => setColsCollapsed(!colsCollapsed)}
              aria-expanded={!colsCollapsed}
            >
              {colsCollapsed ? "Expand Section" : "Collapse Section"}
            </button>
          </div>
        </div>

        {!colsCollapsed && (
          <>
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
                  {visibleColumns.map((col, i) => (
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

            {columns.length > COL_COMPACT_LIMIT && (
              <div className="ar-expand-bar">
                <button
                  type="button"
                  className="ar-expand-btn"
                  onClick={() => setColsExpanded(!colsExpanded)}
                >
                  {colsExpanded
                    ? "Show less (compact view)"
                    : `Show all ${columns.length} columns (+${columns.length - COL_COMPACT_LIMIT} more)`}
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Numeric statistics (Compact Table or Cards + Expandable) ── */}
      {numericEntries.length > 0 && (
        <div className="ar-section">
          <div className="ar-section__header-bar">
            <h3 className="ar-section__title">
              Numeric Statistics
              <span className="ar-section__count">{numericEntries.length} columns</span>
            </h3>
            <div className="ar-section__controls">
              <div className="ar-view-toggle">
                <button
                  type="button"
                  className={`ar-view-btn ${numericMode === "table" ? "active" : ""}`}
                  onClick={() => setNumericMode("table")}
                >
                  Table
                </button>
                <button
                  type="button"
                  className={`ar-view-btn ${numericMode === "cards" ? "active" : ""}`}
                  onClick={() => setNumericMode("cards")}
                >
                  Cards
                </button>
              </div>
              <button
                type="button"
                className="ar-toggle-btn"
                onClick={() => setNumericCollapsed(!numericCollapsed)}
                aria-expanded={!numericCollapsed}
              >
                {numericCollapsed ? "Expand" : "Collapse"}
              </button>
            </div>
          </div>

          {!numericCollapsed && (
            <>
              {numericMode === "table" ? (
                /* Compact Statistics Table */
                <div className="ar-table-wrap" role="region" aria-label="Numeric statistics table" tabIndex={0}>
                  <table className="ar-table ar-table--num">
                    <thead>
                      <tr>
                        <th>Metric Column</th>
                        <th>Mean</th>
                        <th>Median</th>
                        <th>Std Dev</th>
                        <th>Min</th>
                        <th>Max</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(numericExpanded ? numericEntries : numericEntries.slice(0, 6)).map(([col, stats]) => (
                        <tr key={col}>
                          <td className="ar-table__name" title={col}>{col}</td>
                          <td>{fmt(stats.mean)}</td>
                          <td>{fmt(stats.median)}</td>
                          <td>{fmt(stats.std)}</td>
                          <td>{fmt(stats.min)}</td>
                          <td>{fmt(stats.max)}</td>
                          <td>{fmt(stats.count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                /* Detailed Cards Grid */
                <div className="ar-num-grid">
                  {visibleNumericEntries.map(([col, stats]) => (
                    <NumericCard key={col} colName={col} stats={stats} />
                  ))}
                </div>
              )}

              {numericEntries.length > (numericMode === "table" ? 6 : NUM_COMPACT_LIMIT) && (
                <div className="ar-expand-bar">
                  <button
                    type="button"
                    className="ar-expand-btn"
                    onClick={() => setNumericExpanded(!numericExpanded)}
                  >
                    {numericExpanded
                      ? "Show fewer metrics"
                      : `Show all ${numericEntries.length} numeric statistics`}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Categorical summary (Compact & Expandable) ── */}
      {catEntries.length > 0 && (
        <div className="ar-section">
          <div className="ar-section__header-bar">
            <h3 className="ar-section__title">
              Categorical Summary
              <span className="ar-section__count">{catEntries.length} columns</span>
            </h3>
            <div className="ar-section__controls">
              <button
                type="button"
                className="ar-toggle-btn"
                onClick={() => setCatCollapsed(!catCollapsed)}
                aria-expanded={!catCollapsed}
              >
                {catCollapsed ? "Expand Section" : "Collapse Section"}
              </button>
            </div>
          </div>

          {!catCollapsed && (
            <>
              <div className="ar-cat-grid">
                {visibleCatEntries.map(([col, summary]) => (
                  <CategoricalCard key={col} colName={col} summary={summary} />
                ))}
              </div>

              {catEntries.length > CAT_COMPACT_LIMIT && (
                <div className="ar-expand-bar">
                  <button
                    type="button"
                    className="ar-expand-btn"
                    onClick={() => setCatExpanded(!catExpanded)}
                  >
                    {catExpanded
                      ? "Show fewer categories"
                      : `Show all ${catEntries.length} categorical breakdowns (+${catEntries.length - CAT_COMPACT_LIMIT} more)`}
                  </button>
                </div>
              )}
            </>
          )}
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
