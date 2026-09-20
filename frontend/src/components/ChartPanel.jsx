import {
  BarChart, Bar,
  LineChart, Line,
  ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import "./ChartPanel.css";

// ── Constants ─────────────────────────────────────────────────
const H   = 260;   // chart height in pixels
const CLR = {
  bar:      "#6366f1",
  barHover: "#818cf8",
  line:     "#22c55e",
  scatter:  "#a78bfa",
  grid:     "rgba(255,255,255,0.06)",
  axis:     "#475569",
  tick:     "#64748b",
};

// ── Helpers ───────────────────────────────────────────────────
function fmt(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v !== "number") return String(v);
  // Compact thousands: 95000 → "95k", 1200000 → "1.2M"
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000)     return `${(v / 1_000).toFixed(1)}k`;
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function tickFmt(v) {
  if (typeof v !== "number") return v;
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000)     return `${(v / 1_000).toFixed(0)}k`;
  return v;
}

// ── Custom tooltip ────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="cp-tooltip" role="tooltip">
      {label != null && <p className="cp-tooltip__label">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} className="cp-tooltip__row" style={{ color: p.color ?? p.fill ?? "#e2e8f0" }}>
          <span className="cp-tooltip__key">{p.name ?? p.dataKey}:</span>{" "}
          <span className="cp-tooltip__val">{fmt(p.value)}</span>
        </p>
      ))}
    </div>
  );
}

// ── Bar chart card ─────────────────────────────────────────────
function BarCard({ chart }) {
  const longLabels = chart.data.some((d) => String(d.name).length > 8);
  return (
    <div className="cp-card" aria-label={chart.title}>
      <p className="cp-card__title">{chart.title}</p>
      <p className="cp-card__subtitle">{chart.y_label}</p>
      <ResponsiveContainer width="100%" height={H}>
        <BarChart
          data={chart.data}
          margin={{ top: 8, right: 16, left: 4, bottom: longLabels ? 44 : 12 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={CLR.grid} vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: CLR.tick, fontSize: 11 }}
            angle={longLabels ? -28 : 0}
            textAnchor={longLabels ? "end" : "middle"}
            interval={0}
            stroke={CLR.axis}
          />
          <YAxis
            tickFormatter={tickFmt}
            tick={{ fill: CLR.tick, fontSize: 11 }}
            stroke={CLR.axis}
            width={52}
          />
          <Tooltip content={<ChartTooltip />} />
          <Bar
            dataKey="value"
            name={chart.y_label}
            fill={CLR.bar}
            radius={[5, 5, 0, 0]}
            activeBar={{ fill: CLR.barHover }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Line chart card ────────────────────────────────────────────
function LineCard({ chart }) {
  return (
    <div className="cp-card" aria-label={chart.title}>
      <p className="cp-card__title">{chart.title}</p>
      <p className="cp-card__subtitle">{chart.y_label} &mdash; grouped by {chart.x_label}</p>
      <ResponsiveContainer width="100%" height={H}>
        <LineChart
          data={chart.data}
          margin={{ top: 8, right: 16, left: 4, bottom: 12 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={CLR.grid} />
          <XAxis
            dataKey="period"
            tick={{ fill: CLR.tick, fontSize: 11 }}
            stroke={CLR.axis}
          />
          <YAxis
            tickFormatter={tickFmt}
            tick={{ fill: CLR.tick, fontSize: 11 }}
            stroke={CLR.axis}
            width={52}
          />
          <Tooltip content={<ChartTooltip />} />
          <Line
            type="monotone"
            dataKey="value"
            name={chart.y_label}
            stroke={CLR.line}
            strokeWidth={2.5}
            dot={{ r: 4, fill: CLR.line, stroke: "none" }}
            activeDot={{ r: 6, stroke: "rgba(34,197,94,0.4)", strokeWidth: 3 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Scatter chart card ─────────────────────────────────────────
function ScatterCard({ chart }) {
  return (
    <div className="cp-card" aria-label={chart.title}>
      <p className="cp-card__title">{chart.title}</p>
      <p className="cp-card__subtitle">
        {chart.x_label} &times; {chart.y_label} &mdash; {chart.data.length} points
      </p>
      <ResponsiveContainer width="100%" height={H}>
        <ScatterChart margin={{ top: 8, right: 16, left: 4, bottom: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CLR.grid} />
          <XAxis
            dataKey="x"
            name={chart.x_label}
            type="number"
            tickFormatter={tickFmt}
            tick={{ fill: CLR.tick, fontSize: 11 }}
            stroke={CLR.axis}
            label={{
              value: chart.x_label,
              position: "insideBottom",
              offset: -14,
              fill: CLR.tick,
              fontSize: 11,
            }}
          />
          <YAxis
            dataKey="y"
            name={chart.y_label}
            type="number"
            tickFormatter={tickFmt}
            tick={{ fill: CLR.tick, fontSize: 11 }}
            stroke={CLR.axis}
            width={52}
          />
          <Tooltip
            cursor={{ strokeDasharray: "3 3", stroke: CLR.grid }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0]?.payload;
              return (
                <div className="cp-tooltip" role="tooltip">
                  <p className="cp-tooltip__row">
                    <span className="cp-tooltip__key">{chart.x_label}:</span>{" "}
                    <span className="cp-tooltip__val">{fmt(d?.x)}</span>
                  </p>
                  <p className="cp-tooltip__row">
                    <span className="cp-tooltip__key">{chart.y_label}:</span>{" "}
                    <span className="cp-tooltip__val">{fmt(d?.y)}</span>
                  </p>
                </div>
              );
            }}
          />
          <Scatter data={chart.data} fill={CLR.scatter} opacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Chart type badge ───────────────────────────────────────────
const TYPE_LABEL = { bar: "Bar", line: "Line", scatter: "Scatter" };

// ── Main export ────────────────────────────────────────────────
export default function ChartPanel({ charts }) {
  if (!charts?.length) return null;

  return (
    <section className="cp" aria-label="Auto-generated charts">
      <div className="cp-header">
        <h3 className="cp-header__title">Charts</h3>
        <div className="cp-header__tags">
          {charts.map((c, i) => (
            <span key={i} className={`cp-tag cp-tag--${c.type}`}>
              {TYPE_LABEL[c.type] ?? c.type}
            </span>
          ))}
        </div>
      </div>
      <div className="cp-grid">
        {charts.map((chart, i) => {
          if (chart.type === "bar")     return <BarCard     key={i} chart={chart} />;
          if (chart.type === "line")    return <LineCard    key={i} chart={chart} />;
          if (chart.type === "scatter") return <ScatterCard key={i} chart={chart} />;
          return null;
        })}
      </div>
    </section>
  );
}