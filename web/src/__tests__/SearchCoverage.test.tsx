import { describe, test, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchCoverage } from "../components/SearchCoverage";

const base = {
  checked: 20,
  matched: 46,
  limit: 20,
  withAvailability: 5,
  nearby: true,
  driveLimit: true,
  loading: false,
  onCheckRest: () => {},
};

describe("SearchCoverage", () => {
  test("says how many matched when the search was capped", () => {
    render(<SearchCoverage {...base} />);
    expect(
      screen.getByText(/Checked the 20 closest of 46 nearby campgrounds/),
    ).toBeInTheDocument();
    expect(screen.getByText(/5 with availability/)).toBeInTheDocument();
  });

  test("with no drive limit the pool isn't “nearby”; big numbers get separators", () => {
    render(<SearchCoverage {...base} matched={1368} driveLimit={false} />);
    expect(screen.getByText(/^Checked the 20 closest of 1,368 campgrounds —/)).toBeInTheDocument();
  });

  test("a cap per booking system says so instead of contradicting the count", () => {
    render(<SearchCoverage {...base} checked={60} matched={1368} limit={20} driveLimit={false} />);
    expect(screen.getByText(
      /^Checked 60 of 1,368 campgrounds, the 20 closest from each booking system —/,
    )).toBeInTheDocument();
    expect(screen.queryByText(/Showing/)).not.toBeInTheDocument();
  });

  test("keeps the plain wording when nothing was capped", () => {
    render(<SearchCoverage {...base} checked={12} matched={12} />);
    expect(screen.getByText(/^Checked 12 campgrounds/)).toBeInTheDocument();
    expect(screen.queryByText(/ of /)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("one campground is singular", () => {
    render(<SearchCoverage {...base} checked={1} matched={1} withAvailability={0} />);
    expect(screen.getByText(/^Checked 1 campground — 0 with availability/)).toBeInTheDocument();
  });

  test("keeps the plain wording while matched is not yet known", () => {
    render(<SearchCoverage {...base} matched={undefined} />);
    expect(screen.getByText(/^Checked 20 campgrounds/)).toBeInTheDocument();
  });

  test("does not claim 'nearby' when results are not ordered by distance", () => {
    render(<SearchCoverage {...base} nearby={false} />);
    expect(
      screen.getByText(/^Checked 20 of 46 matching campgrounds/),
    ).toBeInTheDocument();
  });

  test("'Check the rest' re-runs with a limit big enough to cover every match", () => {
    const onCheckRest = vi.fn();
    render(<SearchCoverage {...base} matched={46} onCheckRest={onCheckRest} />);
    fireEvent.click(screen.getByRole("button", { name: "Check the rest" }));
    expect(onCheckRest).toHaveBeenCalledWith(46);
  });

  test("matched over the API max of 50 offers no button and says which were checked", () => {
    render(<SearchCoverage {...base} checked={50} matched={120} limit={50} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/^Checked the 50 closest of 120 nearby campgrounds/)).toBeInTheDocument();
  });

  test("a lower limit with matched over 50 reports the limit actually in effect", () => {
    render(<SearchCoverage {...base} matched={120} limit={20} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/^Checked the 20 closest of 120/)).toBeInTheDocument();
  });

  test("while running, counts against the planned total once it is known", () => {
    render(<SearchCoverage {...base} matched={undefined} checked={44} planned={60} loading />);
    expect(screen.getByText(/^Checked 44 of 60 campgrounds — 5 with availability/)).toBeInTheDocument();
  });

  test("while running with no planned total yet, says the count is so far", () => {
    render(<SearchCoverage {...base} matched={undefined} checked={3} loading />);
    expect(screen.getByText(/^Checked 3 campgrounds so far — 5 with availability/)).toBeInTheDocument();
  });

  test("once finished, the planned total no longer shows", () => {
    render(<SearchCoverage {...base} matched={undefined} checked={60} planned={60} />);
    expect(screen.getByText(/^Checked 60 campgrounds — 5 with availability/)).toBeInTheDocument();
  });

  test("no button while the search is still running", () => {
    render(<SearchCoverage {...base} loading />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
