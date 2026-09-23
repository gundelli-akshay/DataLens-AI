import { renderInlineMarkdown } from "../utils/markdown";
import "./MarkdownRenderer.css";

/**
 * Robust Markdown renderer for Groq AI Insights & Document AI Chat.
 * Features:
 * - Markdown tables (| col1 | col2 | and delimiter |---|---|)
 * - Headings (# to ####)
 * - Unordered lists (-, *, •)
 * - Ordered lists (1., 2.)
 * - Blockquotes (>)
 * - Code blocks (```lang ... ```)
 * - Horizontal rules (---, ***, ___)
 * - Paragraphs
 * - Inline formatting: **bold**, *italic*, ***bold-italic***, `code`, badges
 */
export default function MarkdownRenderer({ content, className = "" }) {
  if (!content) return null;

  function renderInline(text) {
    return renderInlineMarkdown(text);
  }

  const rawLines = content.split("\n");
  const blocks = [];
  let i = 0;

  while (i < rawLines.length) {
    const line = rawLines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i++;
      continue;
    }

    // ── Code Block (fenced with ```) ───────────────────────────────
    if (trimmed.startsWith("```")) {
      const codeLines = [];
      i++; // skip opening ```
      while (i < rawLines.length && !rawLines[i].trim().startsWith("```")) {
        codeLines.push(rawLines[i]);
        i++;
      }
      if (i < rawLines.length && rawLines[i].trim().startsWith("```")) {
        i++; // skip closing ```
      }
      blocks.push(
        <pre key={`code-${blocks.length}`} className="ai-md-codeblock">
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    // ── Markdown Table Detection ──────────────────────────────────
    if (trimmed.includes("|") && (trimmed.startsWith("|") || trimmed.endsWith("|"))) {
      const tableLines = [];
      while (
        i < rawLines.length &&
        rawLines[i].trim().includes("|") &&
        (rawLines[i].trim().startsWith("|") || rawLines[i].trim().endsWith("|"))
      ) {
        tableLines.push(rawLines[i].trim());
        i++;
      }

      if (tableLines.length >= 2) {
        const parseRow = (rowStr) => {
          let s = rowStr.trim();
          if (s.startsWith("|")) s = s.slice(1);
          if (s.endsWith("|")) s = s.slice(0, -1);
          return s.split("|").map((c) => c.trim());
        };

        const headers = parseRow(tableLines[0]);
        const isDelimiter = (s) => /^\|?\s*[-:]+[-| :]*\|?$/.test(s);
        const hasDelimiter = isDelimiter(tableLines[1]);
        const dataStartIndex = hasDelimiter ? 2 : 1;
        const dataRows = tableLines.slice(dataStartIndex).map(parseRow);

        blocks.push(
          <div
            key={`table-${blocks.length}`}
            className="ai-table-container"
            tabIndex={0}
            role="region"
            aria-label="Data table"
          >
            <table className="ai-markdown-table">
              <thead>
                <tr>
                  {headers.map((h, hIdx) => (
                    <th key={hIdx}>{renderInline(h)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataRows.map((row, rIdx) => (
                  <tr key={rIdx}>
                    {row.map((cell, cIdx) => {
                      const isCitationCell = /^(?:\(?(?:Page|Paragraph)\s+\d+(?:-\d+)?\)?)$/i.test(cell.trim());
                      return (
                        <td key={cIdx} className={isCitationCell ? "ai-citation-td" : ""}>
                          {renderInline(cell)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        continue;
      }
    }

    // ── Headings ──────────────────────────────────────────────────
    // Standalone bold line acting as section heading (e.g. **Executive Summary**)
    if (/^\*\*[A-Za-z0-9\s&\-.,:]{3,60}\*\*$/.test(trimmed)) {
      const headingText = trimmed.replace(/^\*\*/, '').replace(/\*\*$/, '').replace(/:$/, '').trim();
      blocks.push(
        <h4 key={`bh-${blocks.length}`} className="ai-md-h3">
          {renderInline(headingText)}
        </h4>
      );
      i++;
      continue;
    }

    if (trimmed.startsWith("#### ")) {
      blocks.push(
        <h5 key={`h4-${blocks.length}`} className="ai-md-h4">
          {renderInline(trimmed.replace(/^####\s*/, ""))}
        </h5>
      );
      i++;
      continue;
    }
    if (trimmed.startsWith("### ")) {
      blocks.push(
        <h4 key={`h3-${blocks.length}`} className="ai-md-h3">
          {renderInline(trimmed.replace(/^###\s*/, ""))}
        </h4>
      );
      i++;
      continue;
    }
    if (trimmed.startsWith("## ")) {
      blocks.push(
        <h3 key={`h2-${blocks.length}`} className="ai-md-h2">
          {renderInline(trimmed.replace(/^##\s*/, ""))}
        </h3>
      );
      i++;
      continue;
    }
    if (trimmed.startsWith("# ")) {
      blocks.push(
        <h2 key={`h1-${blocks.length}`} className="ai-md-h1">
          {renderInline(trimmed.replace(/^#\s*/, ""))}
        </h2>
      );
      i++;
      continue;
    }

    // ── Blockquote ────────────────────────────────────────────────
    if (trimmed.startsWith(">")) {
      const quoteLines = [];
      while (i < rawLines.length && rawLines[i].trim().startsWith(">")) {
        quoteLines.push(rawLines[i].trim().replace(/^>\s*/, ""));
        i++;
      }
      blocks.push(
        <blockquote key={`bq-${blocks.length}`} className="ai-md-quote">
          {quoteLines.map((ql, qIdx) => (
            <p key={qIdx}>{renderInline(ql)}</p>
          ))}
        </blockquote>
      );
      continue;
    }

    // ── Horizontal Rule ───────────────────────────────────────────
    if (/^(---|[*]{3}|___)$/.test(trimmed)) {
      blocks.push(<hr key={`hr-${blocks.length}`} className="ai-md-divider" />);
      i++;
      continue;
    }

    // ── Unordered List ────────────────────────────────────────────
    if (/^[-*•]\s+/.test(trimmed)) {
      const listItems = [];
      while (i < rawLines.length && /^[-*•]\s+/.test(rawLines[i].trim())) {
        listItems.push(rawLines[i].trim().replace(/^[-*•]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="ai-md-ul">
          {listItems.map((item, idx) => (
            <li key={idx} className="ai-md-li">
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // ── Ordered List ──────────────────────────────────────────────
    if (/^\d+[.)]\s+/.test(trimmed)) {
      const listItems = [];
      while (i < rawLines.length && /^\d+[.)]\s+/.test(rawLines[i].trim())) {
        listItems.push(rawLines[i].trim().replace(/^\d+[.)]\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={`ol-${blocks.length}`} className="ai-md-ol">
          {listItems.map((item, idx) => (
            <li key={idx} className="ai-md-li">
              {renderInline(item)}
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // ── Paragraph ─────────────────────────────────────────────────
    blocks.push(
      <p key={`p-${blocks.length}`} className="ai-md-p">
        {renderInline(trimmed)}
      </p>
    );
    i++;
  }

  return <div className={`markdown-content ${className}`.trim()}>{blocks}</div>;
}
