import React from "react";

/**
 * Convert markdown bold (**text**) to React <strong> elements safely.
 * Returns an array of ReactNodes alternating between plain strings and <strong>.
 */
function renderBold(text: string): React.ReactNode[] {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return parts.map((part, i) =>
    i % 2 === 1 ? <strong key={i}>{part}</strong> : part,
  );
}

/**
 * Render a markdown string (supporting bold and bullet lists) as safe JSX.
 * Replaces dangerouslySetInnerHTML patterns throughout the app.
 */
export function renderMarkdown(text: string): React.ReactNode {
  const lines = text.trim().split("\n").filter((l) => l.trim());
  const hasBullets = lines.some((l) => l.trim().startsWith("- "));

  if (hasBullets) {
    const items = lines
      .filter((l) => l.trim().startsWith("- "))
      .map((l, i) => <li key={i}>{renderBold(l.trim().replace(/^- /, ""))}</li>);
    return <ul>{items}</ul>;
  }

  return <>{renderBold(text)}</>;
}
