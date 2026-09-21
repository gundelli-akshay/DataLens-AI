import React from "react";

/**
 * Tokenizes text for Markdown inline formatting:
 * - ***bold italic*** or ___bold italic___
 * - **bold** or __bold__
 * - *italic* or _italic_
 * - `inline code`
 * - [Hypothesis] and [Unverified Assumption] analytical tags
 */
export const INLINE_TOKEN_REGEX = /(\*\*\*(?!\s)[^*\n\r]+?(?<!\s)\*\*\*|___(?!\s)[^_\n\r]+?(?<!\s)___|\*\*(?!\s)[^*\n\r]+?(?<!\s)\*\*|__(?!\s)[^_\n\r]+?(?<!\s)__|(?<!\*)\*(?!\s|\*)[^*\n\r]+?(?<!\s|\*)\*(?!\*)|(?<!_)_(?!\s|_)[^_\n\r]+?(?<!\s|_)_(?!_)|`[^`\n\r]+`|\[Hypothesis\]|\[Unverified Assumption\])/g;

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
    return part;
  });
}
