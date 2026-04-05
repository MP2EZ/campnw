import { describe, test, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("../api", () => ({
  track: vi.fn(),
}));

import { DateRangePicker } from "../components/DateRangePicker";

describe("DateRangePicker", () => {
  const defaultProps = {
    startDate: "2026-06-01",
    endDate: "2026-06-30",
    onChange: vi.fn(),
  };

  test('renders "Search between" label for mode="find"', () => {
    render(<DateRangePicker {...defaultProps} mode="find" />);
    expect(screen.getByText("Search between")).toBeInTheDocument();
  });

  test('renders "Check in – out" label for mode="exact"', () => {
    render(<DateRangePicker {...defaultProps} mode="exact" />);
    expect(screen.getByText("Check in – out")).toBeInTheDocument();
  });

  test("formats same-month range correctly", () => {
    render(<DateRangePicker {...defaultProps} mode="find" />);
    expect(screen.getByText("Jun 1 – 30")).toBeInTheDocument();
  });

  test("formats cross-month range correctly", () => {
    render(
      <DateRangePicker
        startDate="2026-04-19"
        endDate="2026-05-19"
        onChange={vi.fn()}
        mode="find"
      />
    );
    expect(screen.getByText("Apr 19 – May 19")).toBeInTheDocument();
  });

  test("opens popover on click", () => {
    render(<DateRangePicker {...defaultProps} mode="find" />);
    const trigger = screen.getByRole("button", { name: /Search between/ });
    fireEvent.click(trigger);
    // When open, month title text becomes visible
    expect(screen.getByText("June 2026")).toBeInTheDocument();
  });

  test("closes on Escape key", () => {
    render(<DateRangePicker {...defaultProps} mode="find" />);
    const trigger = screen.getByRole("button", { name: /Search between/ });
    fireEvent.click(trigger);
    expect(screen.getByText("June 2026")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("June 2026")).not.toBeInTheDocument();
  });

  test("past dates are disabled", () => {
    render(
      <DateRangePicker
        startDate="2020-01-01"
        endDate="2020-01-31"
        onChange={vi.fn()}
        mode="find"
      />
    );
    const trigger = screen.getByRole("button", { name: /Search between/ });
    fireEvent.click(trigger);

    // All days in Jan 2020 should be disabled (they are in the past)
    const dayButtons = screen.getAllByRole("button", { name: /January/ });
    for (const btn of dayButtons) {
      expect(btn).toBeDisabled();
    }
  });

  test("aria-expanded reflects open state", () => {
    render(<DateRangePicker {...defaultProps} mode="find" />);
    const trigger = screen.getByRole("button", { name: /Search between/ });

    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});
