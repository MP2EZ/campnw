import { describe, test, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { SearchResponse } from "../api";
import { ResultsNotices } from "../results/ResultsNotices";

const results = (kind: string): SearchResponse => ({
  campgrounds_checked: 20,
  campgrounds_with_availability: 0,
  results: [],
  warnings: [{ kind, count: 13, source: "or_state", message: "Still checking 13 Oregon State Parks campgrounds." }],
});

describe("ResultsNotices", () => {
  test("a still-checking warning offers Check again, which re-runs the search", () => {
    const onCheckAgain = vi.fn();
    render(<ResultsNotices results={results("pending")} onCheckAgain={onCheckAgain} />);
    screen.getByRole("button", { name: "Check again" }).click();
    expect(onCheckAgain).toHaveBeenCalledOnce();
  });

  test("other warnings don't", () => {
    render(<ResultsNotices results={results("timeout")} onCheckAgain={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Check again" })).toBeNull();
  });

  test("no button while the search is running", () => {
    render(<ResultsNotices results={results("pending")} />);
    expect(screen.queryByRole("button", { name: "Check again" })).toBeNull();
  });
});
