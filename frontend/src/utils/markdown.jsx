import React from "react";

/**
 * Tokenizes text for Markdown inline formatting:
 * - ***bold italic*** or ___bold italic___
 * - **bold** or __bold__
 * - *italic* or _italic_
 * - `inline code`
 * - [Hypothesis] and [Unverified Assumption] analytical tags
 * - (Page X), (Paragraph Y), Page X, Paragraph Y citations
 */
export const INLINE_TOKEN_REGEX = /(\*{3}(?!\s)[^*\n\r]+?(?<!\s)\*{3}|_{3}(?!\s)[^_\n\r]+?(?<!\s)_{3}|\*{2}(?!\s)[^*\n\r]+?(?<!\s)\*{2}|_{2}(?!\s)[^_\n\r]+?(?<!\s)_{2}|(?<!\*)\*(?!\s|\*)[^*\n\r]+?(?<!\s|\*)\*(?!\*)|(?<!_)_(?!\s|_)[^_\n\r]+?(?<!\s|_)_(?!_)|`[^`\n\r]+`|\[Hypothesis\]|\[Unverified Assumption\]|\((?:Page|Paragraph)\s+\d+(?:-\d+)?\)|\[(?:Page|Paragraph)\s+\d+(?:-\d+)?\]|\b(?:Page|Paragraph)\s+\d+(?:-\d+)?\b)/gi;

const CITATION_TOKEN_REGEX = /^(?:\((?:Page|Paragraph)\s+\d+(?:-\d+)?\)|\[(?:Page|Paragraph)\s+\d+(?:-\d+)?\]|(?:Page|Paragraph)\s+\d+(?:-\d+)?)$/i;

export function renderInlineMarkdown(text) {
  if (!text) return "";

  const parts = text.split(INLINE_TOKEN_REGEX);
  return parts.map((part, i) => {
    if (!part) return null;
    if ((part.startsWith("***") && part.endsWith("***")) || (part.startsWith("___") && part.endsWith("___"))) {
      return (
        <strong key={i}>
          <em>{part.slice(3, -3)}</em>
        </strong>
      );
    }
    if ((part.startsWith("**") && part.endsWith("**")) || (part.startsWith("__") && part.endsWith("__"))) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"))) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="ai-inline-code">{part.slice(1, -1)}</code>;
    }
    if (part === "[Hypothesis]") {
      return (
        <span key={i} className="ai-badge-hypothesis" title="Analytical hypothesis - not a measured fact">
          Hypothesis
        </span>
      );
    }
    if (part === "[Unverified Assumption]") {
      return (
        <span key={i} className="ai-badge-assumption" title="Unverified domain assumption">
          Unverified Assumption
        </span>
      );
    }
    if (CITATION_TOKEN_REGEX.test(part.trim())) {
      return (
        <span key={i} className="ai-citation-inline" title="Verified source location">
          {part}
        </span>
      );
    }
    return part;
  });
}
