import { describe, test, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

vi.mock("../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  },
}));

const proStatus = {
  subscription_status: "pro",
  subscription_expires_at: "",
  has_stripe_customer: true,
  is_pro: true,
  watch_limit: null,
  planner_session_limit: 20,
  configured: true,
};

/** Renders isPro and watchLimit from the freshly imported useBilling. */
const limitProbe = (useBilling: () => { isPro: boolean; watchLimit: number | null; loading: boolean }) =>
  function Probe() {
    const { isPro, watchLimit, loading } = useBilling();
    if (loading) return <span>loading</span>;
    return (
      <span data-testid="probe">
        pro:{String(isPro)} limit:{String(watchLimit)}
      </span>
    );
  };

/** Stubs the hooks the next dynamic import of a component will read. */
const mockAuthBilling = (user: object | null, billing: object) => {
  vi.doMock("../hooks/useAuth", () => ({ useAuth: () => ({ user }) }));
  vi.doMock("../hooks/useBilling", () => ({ useBilling: () => billing }));
};

const inRouter = (ui: ReactElement) =>
  render(<MemoryRouter>{ui}</MemoryRouter>);

describe("api: WatchLimitError on 402", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  test("createWatch throws WatchLimitError when body shape matches", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 402,
      json: () =>
        Promise.resolve({
          detail: {
            error: "watch_limit_reached",
            limit: 3,
            current: 3,
            upgrade_url: "/pricing",
          },
        }),
    });
    globalThis.fetch = mockFetch;

    const { createWatch, WatchLimitError } = await import("../api");

    let caught: unknown = null;
    try {
      await createWatch({
        facility_id: "x",
        name: "x",
        start_date: "2026-07-01",
        end_date: "2026-07-07",
        min_nights: 1,
      });
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(WatchLimitError);
    expect((caught as InstanceType<typeof WatchLimitError>).limit).toBe(3);
    expect((caught as InstanceType<typeof WatchLimitError>).current).toBe(3);
    expect((caught as InstanceType<typeof WatchLimitError>).upgradeUrl).toBe(
      "/pricing",
    );
  });

  test("createWatch throws generic Error for non-402 failure", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({}),
    });
    const { createWatch, WatchLimitError } = await import("../api");
    const failure = createWatch({
      facility_id: "x",
      name: "x",
      start_date: "2026-07-01",
      end_date: "2026-07-07",
      min_nights: 1,
    });
    await expect(failure).rejects.toThrow();
    await expect(failure).rejects.not.toBeInstanceOf(WatchLimitError);
  });

  test("getBillingStatus parses BillingStatus shape", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve(proStatus),
    });
    const { getBillingStatus } = await import("../api");
    const status = await getBillingStatus();
    expect(status.is_pro).toBe(true);
    expect(status.watch_limit).toBeNull();
  });

  test("startCheckout returns URL on 200", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ url: "https://checkout.stripe.com/x" }),
    });
    const { startCheckout } = await import("../api");
    const url = await startCheckout();
    expect(url).toBe("https://checkout.stripe.com/x");
  });

  test("startCheckout throws with detail on non-200", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: () => Promise.resolve({ detail: "Billing is not configured" }),
    });
    const { startCheckout } = await import("../api");
    await expect(startCheckout()).rejects.toThrow(
      "Billing is not configured",
    );
  });

  test("planChatStream reports PlannerLimitError on 402 with matching payload", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 402,
      json: () =>
        Promise.resolve({
          detail: {
            error: "planner_session_limit_reached",
            limit: 3,
            current: 3,
            upgrade_url: "/pricing",
          },
        }),
    });
    const { planChatStream, PlannerLimitError } = await import("../api");
    let caught: unknown = null;
    await planChatStream(
      [{ role: "user", content: "x" }],
      vi.fn(), vi.fn(), vi.fn(), vi.fn(),
      (e) => { caught = e; },
    );
    expect(caught).toBeInstanceOf(PlannerLimitError);
    expect((caught as InstanceType<typeof PlannerLimitError>).limit).toBe(3);
  });

  test("planChatStream sends the conversation id and reports the server's", async () => {
    const body = new ReadableStream({
      start(c) {
        c.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
        c.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "X-Plan-Conversation": "b".repeat(32) }),
      body,
    });
    globalThis.fetch = fetchMock;
    const { planChatStream } = await import("../api");
    const onConversation = vi.fn();
    await planChatStream(
      [{ role: "user", content: "x" }],
      vi.fn(), vi.fn(), vi.fn(), vi.fn(), vi.fn(),
      "a".repeat(32), onConversation,
    );
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent.conversation_id).toBe("a".repeat(32));
    expect(onConversation).toHaveBeenCalledWith("b".repeat(32));
  });
});

describe("useBilling", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  test("provider falls back to free shape when /api/billing/status fails", async () => {
    vi.doMock("../hooks/useAuth", () => ({
      useAuth: () => ({ user: null, loading: false }),
    }));
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("offline"));

    const { BillingProvider, useBilling } = await import("../hooks/useBilling");

    const Probe = limitProbe(useBilling);

    render(
      <BillingProvider>
        <Probe />
      </BillingProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent(
        "pro:false limit:3",
      );
    });
  });

  test("provider reflects Pro status from server", async () => {
    vi.doMock("../hooks/useAuth", () => ({
      useAuth: () => ({
        user: { id: 1, email: "p@x.com", display_name: "P" },
        loading: false,
      }),
    }));
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve(proStatus),
    });

    const { BillingProvider, useBilling } = await import("../hooks/useBilling");

    const Probe = limitProbe(useBilling);

    render(
      <BillingProvider>
        <Probe />
      </BillingProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent(
        "pro:true limit:null",
      );
    });
  });

  test("strips ?billing=success from URL after refresh", async () => {
    // Stripe Checkout success redirect lands at /?billing=success. The
    // hook must call refresh() (so PRO badge appears) AND clean the URL
    // (so a bookmark or share doesn't carry the noise). Without the
    // cleanup, the badge would still appear but the URL would persist
    // through navigation, polluting analytics and breaking later
    // billing=cancelled scenarios that reuse the same param.
    const originalHistory = window.history.replaceState;
    const replaceStateMock = vi.fn();
    Object.defineProperty(window, "history", {
      value: { ...window.history, replaceState: replaceStateMock },
      writable: true,
    });
    Object.defineProperty(window, "location", {
      value: {
        ...window.location,
        search: "?billing=success",
        pathname: "/",
      },
      writable: true,
    });

    vi.doMock("../hooks/useAuth", () => ({
      useAuth: () => ({
        user: { id: 1, email: "u@x.com", display_name: "U" },
        loading: false,
      }),
    }));
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve(proStatus),
    });

    const { BillingProvider } = await import("../hooks/useBilling");
    render(
      <BillingProvider>
        <div />
      </BillingProvider>,
    );

    await waitFor(() => {
      expect(replaceStateMock).toHaveBeenCalled();
    });
    // Newly-replaced URL must not contain the billing=success param
    const replaceArgs = replaceStateMock.mock.calls[0];
    expect(replaceArgs[2]).not.toContain("billing=success");

    // Restore
    Object.defineProperty(window.history, "replaceState", {
      value: originalHistory,
    });
  });

  test("a Portal return is not a checkout, and re-reads until the webhook lands", async () => {
    // The Portal used to return to ?billing=success, so every cancel was
    // logged as checkout_returned and status was read exactly once — before
    // Stripe's webhook had updated it. The user saw plain "Pro" after
    // cancelling until they reloaded.
    const originalHistory = window.history.replaceState;
    const replaceStateMock = vi.fn();
    Object.defineProperty(window, "history", {
      value: { ...window.history, replaceState: replaceStateMock },
      writable: true,
    });
    Object.defineProperty(window, "location", {
      value: { ...window.location, search: "?billing=portal", pathname: "/" },
      writable: true,
    });
    const capture = vi.fn();
    (window as unknown as { posthog: unknown }).posthog = {
      capture,
      register: vi.fn(),
    };

    vi.doMock("../hooks/useAuth", () => ({
      useAuth: () => ({
        user: { id: 1, email: "u@x.com", display_name: "U" },
        loading: false,
      }),
    }));
    // Real schedule, no real waiting.
    vi.doMock("../lib/pollUntilChanged", async () => {
      const actual = await vi.importActual<
        typeof import("../lib/pollUntilChanged")
      >("../lib/pollUntilChanged");
      return {
        pollUntilChanged: (o: Parameters<typeof actual.pollUntilChanged>[0]) =>
          actual.pollUntilChanged({ ...o, sleep: () => Promise.resolve() }),
      };
    });

    let reads = 0;
    globalThis.fetch = vi.fn().mockImplementation(async () => {
      reads += 1;
      // Webhook lands on the third read.
      const expires = reads >= 3 ? "2026-11-28T00:00:00Z" : "";
      return {
        ok: true,
        json: () => Promise.resolve({ ...proStatus, subscription_expires_at: expires }),
      };
    });

    const { BillingProvider, useBilling } = await import("../hooks/useBilling");
    function Probe() {
      const { status } = useBilling();
      return <span data-testid="probe">{status?.subscription_expires_at || "none"}</span>;
    }
    render(
      <BillingProvider>
        <Probe />
      </BillingProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("2026-11-28");
    });
    expect(capture).toHaveBeenCalledWith("portal_returned", expect.anything());
    expect(capture).not.toHaveBeenCalledWith("checkout_returned", expect.anything());
    expect(replaceStateMock.mock.calls[0][2]).not.toContain("billing=portal");

    delete (window as unknown as { posthog?: unknown }).posthog;
    Object.defineProperty(window.history, "replaceState", {
      value: originalHistory,
    });
  });
});

describe("UpgradeModal", () => {
  const mockStartCheckout = vi.fn();

  beforeEach(() => {
    vi.resetModules();
    mockStartCheckout.mockReset();
    vi.doMock("../api", () => ({
      track: vi.fn(),
    }));
  });

  test("renders nothing when open=false", async () => {
    mockAuthBilling(null, {
      startCheckout: mockStartCheckout,
      status: { configured: true },
    });
    const { UpgradeModal } = await import("../components/UpgradeModal");
    const { container } = render(
      <UpgradeModal open={false} onClose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  test("shows watch_limit headline when reason=watch_limit", async () => {
    mockAuthBilling({ id: 1, email: "x@x.com" }, {
      startCheckout: mockStartCheckout,
      status: { configured: true },
    });
    const { UpgradeModal } = await import("../components/UpgradeModal");
    render(
      <UpgradeModal open={true} onClose={() => {}} reason="watch_limit" />,
    );
    expect(
      screen.getByRole("heading", { name: /unlimited watches/i }),
    ).toBeInTheDocument();
  });

  test("Upgrade button calls startCheckout for logged-in user", async () => {
    mockAuthBilling({ id: 1, email: "x@x.com" }, {
      startCheckout: mockStartCheckout,
      status: { configured: true },
    });
    const { UpgradeModal } = await import("../components/UpgradeModal");
    render(<UpgradeModal open={true} onClose={() => {}} />);
    fireEvent.click(
      screen.getByRole("button", { name: /upgrade to pro/i }),
    );
    await waitFor(() => {
      expect(mockStartCheckout).toHaveBeenCalledOnce();
    });
  });

  test("shows sign-in prompt instead of CTA when anonymous", async () => {
    mockAuthBilling(null, {
      startCheckout: mockStartCheckout,
      status: { configured: true },
    });
    const { UpgradeModal } = await import("../components/UpgradeModal");
    render(<UpgradeModal open={true} onClose={() => {}} />);
    expect(screen.getByText(/sign in first/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /upgrade to pro/i }),
    ).not.toBeInTheDocument();
  });

  test("shows 'not live yet' note when Stripe unconfigured", async () => {
    mockAuthBilling({ id: 1, email: "x@x.com" }, {
      startCheckout: mockStartCheckout,
      status: { configured: false },
    });
    const { UpgradeModal } = await import("../components/UpgradeModal");
    render(<UpgradeModal open={true} onClose={() => {}} />);
    expect(screen.getByText(/aren.t live yet/i)).toBeInTheDocument();
  });

  test("ESC key closes the modal", async () => {
    const onClose = vi.fn();
    mockAuthBilling(null, {
      startCheckout: mockStartCheckout,
      status: { configured: true },
    });
    const { UpgradeModal } = await import("../components/UpgradeModal");
    render(<UpgradeModal open={true} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("Pricing page", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.doMock("../api", () => ({
      track: vi.fn(),
    }));
  });

  test("renders Free + Pro cards with prices", async () => {
    mockAuthBilling(null, {
      isPro: false,
      loading: false,
      status: { configured: false },
      startCheckout: vi.fn(),
      openPortal: vi.fn(),
    });
    const Pricing = (await import("../pages/Pricing")).default;
    inRouter(<Pricing />);
    expect(screen.getByRole("heading", { name: /pricing that pays/i })).toBeInTheDocument();
    expect(screen.getByText("$0")).toBeInTheDocument();
    // $5 appears in both the pricing card and the comparison table
    expect(screen.getAllByText(/\$5/).length).toBeGreaterThan(0);
  });

  test("shows 'Sign in to upgrade' for anonymous users", async () => {
    mockAuthBilling(null, {
      isPro: false,
      loading: false,
      status: { configured: true },
      startCheckout: vi.fn(),
      openPortal: vi.fn(),
    });
    const Pricing = (await import("../pages/Pricing")).default;
    inRouter(<Pricing />);
    expect(screen.getByText(/sign in to upgrade/i)).toBeInTheDocument();
  });

  test("shows 'Manage billing' for Pro users", async () => {
    mockAuthBilling({ id: 1, email: "p@x.com" }, {
      isPro: true,
      loading: false,
      status: { configured: true },
      startCheckout: vi.fn(),
      openPortal: vi.fn(),
    });
    const Pricing = (await import("../pages/Pricing")).default;
    inRouter(<Pricing />);
    expect(
      screen.getByRole("button", { name: /manage billing/i }),
    ).toBeInTheDocument();
  });

  test("shows 'Upgrade to Pro' button for free user when configured", async () => {
    mockAuthBilling({ id: 1, email: "f@x.com" }, {
      isPro: false,
      loading: false,
      status: { configured: true },
      startCheckout: vi.fn(),
      openPortal: vi.fn(),
    });
    const Pricing = (await import("../pages/Pricing")).default;
    inRouter(<Pricing />);
    expect(
      screen.getByRole("button", { name: /upgrade to pro/i }),
    ).toBeInTheDocument();
  });
});

describe("ProBadge", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  test("renders nothing for free users", async () => {
    vi.doMock("../hooks/useBilling", () => ({
      useBilling: () => ({ isPro: false }),
    }));
    const { ProBadge } = await import("../components/ProBadge");
    const { container } = inRouter(<ProBadge />);
    expect(container.querySelector(".pro-badge")).toBeNull();
  });

  test("renders Pro link for Pro users", async () => {
    vi.doMock("../hooks/useBilling", () => ({
      useBilling: () => ({ isPro: true }),
    }));
    const { ProBadge } = await import("../components/ProBadge");
    inRouter(<ProBadge />);
    const badge = screen.getByText("Pro");
    expect(badge).toBeInTheDocument();
    expect(badge.closest("a")).toHaveAttribute("href", "/pricing");
  });
});
