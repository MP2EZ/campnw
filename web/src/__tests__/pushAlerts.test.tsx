import { describe, test, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../api", () => ({ track: vi.fn() }));

import { parsePushAlert, providerLabel } from "../lib/pushAlerts";
import { PushAlertSheet } from "../components/PushAlertSheet";

const data = {
  aps: { alert: { title: "Ohanapecosh: site open", body: "Fri Jun 12 · Site 23 (Loop B). Book on Recreation.gov." } },
  watch_id: 42,
  booking_url: "https://www.recreation.gov/camping/campgrounds/232465",
  path: "/?alert=42",
};

describe("parsePushAlert", () => {
  test("reads the alert the server sends", () => {
    expect(parsePushAlert(data)).toEqual({
      watchId: 42,
      title: "Ohanapecosh: site open",
      body: "Fri Jun 12 · Site 23 (Loop B). Book on Recreation.gov.",
      bookingUrl: "https://www.recreation.gov/camping/campgrounds/232465",
    });
  });

  test("falls back to the notification's own title and body", () => {
    expect(parsePushAlert({ ...data, aps: undefined }, "T", "B")).toMatchObject({ title: "T", body: "B" });
  });

  test.each([
    ["javascript:alert(1)"], ["http://www.recreation.gov/x"], ["app-settings:"], ["not a url"], [42],
  ])("drops alerts whose booking link isn't https: %s", (booking_url) => {
    expect(parsePushAlert({ ...data, booking_url })).toBeNull();
  });

  test.each([[null], ["x"], [{}], [{ ...data, watch_id: "abc" }], [{ ...data, watch_id: -1 }]])(
    "ignores other payloads: %s", (d) => {
      expect(parsePushAlert(d)).toBeNull();
    },
  );
});

describe("PushAlertSheet", () => {
  test("names the provider and opens the booking link outside the app", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const onClose = vi.fn();
    const alert = parsePushAlert(data)!;
    render(<PushAlertSheet alert={alert} onClose={onClose} onOpenWatchlist={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Ohanapecosh: site open" })).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: "Book on Recreation.gov" }));
    expect(open).toHaveBeenCalledWith(alert.bookingUrl, "_blank");
    expect(onClose).toHaveBeenCalled();
  });

  test("can go to the watchlist instead", async () => {
    const onOpenWatchlist = vi.fn();
    render(<PushAlertSheet alert={parsePushAlert(data)!} onClose={vi.fn()} onOpenWatchlist={onOpenWatchlist} />);
    await userEvent.click(screen.getByRole("button", { name: "See my watchlist" }));
    expect(onOpenWatchlist).toHaveBeenCalled();
  });

  test.each([
    ["https://washington.goingtocamp.com/create-booking/results?x=1", "WA State Parks"],
    ["https://www.reserveamerica.com/explore/x", "ReserveAmerica"],
    ["https://evil-recreation.gov.example/x", "evil-recreation.gov.example"],
  ])("provider label for %s", (url, label) => {
    expect(providerLabel(url)).toBe(label);
  });
});
