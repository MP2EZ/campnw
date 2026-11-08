import type { ComponentProps } from "react";
import { SearchCoverage } from "../components/SearchCoverage";

interface Props {
  sentence: string;
  coverage: ComponentProps<typeof SearchCoverage>;
  /** "searched just now", or null while the search is still running. */
  searched: string | null;
}

/**
 * The answer first, then how much was checked. An h2 until the v2 header
 * replaces the wordmark's h1 (P3a); then this becomes the page's h1.
 */
export function AnswerHeader({ sentence, coverage, searched }: Props) {
  return (
    <div className="rv2-answer">
      <h2 id="rv2-answer" className="rv2-answer-line">{sentence}</h2>
      <SearchCoverage {...coverage} after={searched && ` · ${searched}`} />
    </div>
  );
}
