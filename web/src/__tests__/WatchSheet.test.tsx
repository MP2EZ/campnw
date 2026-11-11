import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CampgroundResult, SearchParams } from "../api";
import { WatchSheet } from "../results/WatchSheet";

const auth = vi.hoisted(() => ({ user: { id: 2 } as unknown }));
const api = vi.hoisted(() => ({ createWatch: vi.fn(), track: vi.fn() }));

vi.mock("../hooks/useAuth", () => ({ useAuth: () => ({ user: auth.user }) }));
vi.mock("../hooks/useBilling", () => ({
  useBilling: () => ({ isPro: false, watchLimit: 3, status: null, startCheckout: vi.fn() }),
}));
vi.mock("../hooks/usePushNotifications", () => ({
  usePushNotifications: () => ({ permission: "default", subscribed: false, subscribe: vi.fn() }),
}));
vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), ...api }));

const params: SearchParams = {
  start_date: "2027-06-01", end_date: "2027-06-30", mode: "find", nights: 2, days_of_week: "4,5,6",
  people: 4, equipment: "trailer", rig_length: 30,
};
const place = { facility_id: "232465", name: "Kachess", booking_system: "recgov", windows: [] } as unknown as CampgroundResult;
const stays = [
  { start: "2027-06-04", end: "2027-06-06", label: "Fri Jun 4 – Sun 6" },
  { start: "2027-06-18", end: "2027-06-20", label: "Fri Jun 18 – Sun 20" },
];

function renderSheet(extra: Partial<Parameters<typeof WatchSheet>[0]> = {}) {
  const onClose = vi.fn();
  const onSignIn = vi.fn();
  render(<WatchSheet place={place} params={params} stays={stays} initial="2027-06-18" from="chip"
    onClose={onClose} onSignIn={onSignIn} {...extra} />);
  return { onClose, onSignIn, dialog: screen.getByRole("dialog", { name: "Watch Kachess" }) };
}

beforeEach(() => {
  auth.user = { id: 2 };
  api.createWatch.mockReset().mockResolvedValue({ id: 1 });
  api.track.mockReset();
});

describe("WatchSheet", () => {
  test("starts on the chosen stay with the search's party and rig", () => {
    const { dialog } = renderSheet();
    expect(within(dialog).getByRole("radio", { name: /Fri Jun 18 – Sun 20/ })).toBeChecked();
    expect(dialog).toHaveTextContent("4 people · 30′ trailer");
    expect(within(dialog).getByRole("radio", { name: "Any site that fits" })).toBeChecked();
    expect(within(dialog).getByRole("heading", { name: "Watch Kachess" })).toHaveFocus();
  });

  test("creates one watch for that stay, with the filters, and says so", async () => {
    renderSheet({ from: "full_group" });
    await userEvent.click(screen.getByRole("radio", { name: "Only sites with hookups" }));
    await userEvent.click(screen.getByRole("button", { name: "Start watching Fri Jun 18 – Sun 20" }));
    expect(api.createWatch).toHaveBeenCalledWith({
      facility_id: "232465", name: "Kachess", start_date: "2027-06-18", end_date: "2027-06-20",
      min_nights: 2, notification_channel: "web_push",
      min_people: 4, equipment: "trailer", rig_length: 30, site_types: ["hookups"],
    });
    expect(api.track).toHaveBeenCalledWith("watch_created", expect.objectContaining({
      from: "full_group", has_filters: 1, ui_version: "v2",
    }));
    expect(await screen.findByText(/Watching Fri Jun 18 – Sun 20/)).toHaveFocus();
    expect(screen.getByRole("button", { name: "Turn on notifications" })).toBeInTheDocument();
  });

  test("the party and rig can be changed before watching", async () => {
    renderSheet();
    await userEvent.click(screen.getByRole("button", { name: "Change party and rig" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Rig" }), "tent");
    expect(screen.queryByRole("spinbutton", { name: "Length (ft)" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Start watching/ }));
    const req = api.createWatch.mock.calls[0][0];
    expect(req.equipment).toBe("tent");
    expect(req).not.toHaveProperty("rig_length");
  });

  test("a duplicate or a failed request is shown, not swallowed", async () => {
    api.createWatch.mockRejectedValueOnce(new Error("Failed to create watch: 409"));
    renderSheet();
    await userEvent.click(screen.getByRole("button", { name: /Start watching/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already watching Kachess");

    api.createWatch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await userEvent.click(screen.getByRole("button", { name: /Start watching/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't start the watch");
    expect(api.track).not.toHaveBeenCalled();
  });

  test("the free-tier limit opens the existing upgrade modal", async () => {
    const { WatchLimitError } = await import("../api");
    api.createWatch.mockRejectedValueOnce(new WatchLimitError({ limit: 3, current: 3, upgrade_url: "/pricing" }));
    renderSheet();
    await userEvent.click(screen.getByRole("button", { name: /Start watching/ }));
    expect(await screen.findByRole("dialog", { name: "Upgrade for unlimited watches" })).toBeInTheDocument();
  });

  test("signed out, the sheet hands over to sign-in", async () => {
    auth.user = null;
    const { onClose, onSignIn } = renderSheet();
    await userEvent.click(screen.getByRole("button", { name: "Sign in to watch" }));
    expect(onClose).toHaveBeenCalled();
    expect(onSignIn).toHaveBeenCalled();
    expect(api.createWatch).not.toHaveBeenCalled();
  });

  test("Escape and the close button close it", async () => {
    const { onClose } = renderSheet();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  test("one stay is stated, not offered as a choice", () => {
    const { dialog } = renderSheet({ stays: [stays[0]], initial: undefined });
    expect(within(dialog).queryByRole("radio", { name: /Fri Jun/ })).not.toBeInTheDocument();
    expect(dialog).toHaveTextContent("Fri Jun 4 – Sun 6 · Full now");
  });
});
