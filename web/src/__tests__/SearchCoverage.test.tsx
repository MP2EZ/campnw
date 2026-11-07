import { describe, test, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchCoverage } from "../components/SearchCoverage";

const base = {
  checked: 20,
  matched: 46,
  limit: 20,
  withAvailability: 5,
  nearby: true,
  loading: false,
  onCheckRest: () => {},
};

describe("SearchCoverage", () => {
  test("says how many matched when the search was capped", () => {
    render(<SearchCoverage {...base} />);
    expect(
      screen.getByText(/Checked 20 of 46 nearby campgrounds/),
    ).toBeInTheDocument();
    expect(screen.getByText(/5 with availability/)).toBeInTheDocument();
  });

  test("keeps the plain wording when nothing was capped", () => {
    render(<SearchCoverage {...base} checked={12} matched={12} />);
    expect(screen.getByText(/^Checked 12 campgrounds/)).toBeInTheDocument();
    expect(screen.queryByText(/ of /)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("keeps the plain wording while matched is not yet known", () => {
    render(<SearchCoverage {...base} matched={undefined} />);
    expect(screen.getByText(/^Checked 20 campgrounds/)).toBeInTheDocument();
  });

  test("does not claim 'nearby' when results are not ordered by distance", () => {
    render(<SearchCoverage {...base} nearby={false} />);
    expect(
      screen.getByText(/Checked 20 of 46 matching campgrounds/),
    ).toBeInTheDocument();
  });

  test("'Check the rest' re-runs with a limit big enough to cover every match", () => {
    const onCheckRest = vi.fn();
    render(<SearchCoverage {...base} matched={46} onCheckRest={onCheckRest} />);
    fireEvent.click(screen.getByRole("button", { name: "Check the rest" }));
    expect(onCheckRest).toHaveBeenCalledWith(46);
  });

  test("matched over the API max of 50 offers no button and says what is shown", () => {
    render(<SearchCoverage {...base} checked={50} matched={120} limit={50} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/Checked 50 of 120/)).toBeInTheDocument();
    expect(screen.getByText(/Showing the 50 closest/)).toBeInTheDocument();
  });

  test("a lower limit with matched over 50 reports the limit actually in effect", () => {
    render(<SearchCoverage {...base} matched={120} limit={20} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/Showing the 20 closest/)).toBeInTheDocument();
  });

  test("no button while the search is still running", () => {
    render(<SearchCoverage {...base} loading />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
