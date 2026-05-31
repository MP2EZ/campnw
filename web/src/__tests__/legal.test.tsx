import { describe, test, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import Privacy from "../pages/Privacy";
import Terms from "../pages/Terms";

function renderPage(page: React.ReactElement) {
  return render(
    <HelmetProvider>
      <MemoryRouter>{page}</MemoryRouter>
    </HelmetProvider>,
  );
}

describe("Privacy page", () => {
  test("renders the h1 and last-updated stamp", () => {
    renderPage(<Privacy />);
    expect(
      screen.getByRole("heading", { level: 1, name: /privacy policy/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/last updated: 2026-05-31/i)).toBeInTheDocument();
  });

  test("names every third-party service we share data with", () => {
    // Guards against drift: if someone adds a new third-party
    // integration and forgets to update Privacy, this test fires.
    renderPage(<Privacy />);
    const required = [
      "Supabase",
      "Stripe",
      "PostHog",
      "Mapbox",
      "Visual Crossing",
      "Cloudflare",
    ];
    for (const name of required) {
      const matches = screen.getAllByText(new RegExp(name));
      expect(matches.length).toBeGreaterThan(0);
    }
  });

  test("links to the support email", () => {
    renderPage(<Privacy />);
    const mailtos = screen.getAllByRole("link", {
      name: /hello@palouselabs\.com/i,
    });
    expect(mailtos.length).toBeGreaterThan(0);
    expect(mailtos[0].getAttribute("href")).toBe(
      "mailto:hello@palouselabs.com",
    );
  });
});

describe("Terms page", () => {
  test("renders the h1 and last-updated stamp", () => {
    renderPage(<Terms />);
    expect(
      screen.getByRole("heading", { level: 1, name: /terms of service/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/last updated: 2026-05-31/i)).toBeInTheDocument();
  });

  test("states the 30-day refund policy explicitly", () => {
    // Stripe's account-review keyword scan looks for the phrase.
    renderPage(<Terms />);
    expect(
      screen.getByRole("heading", { level: 2, name: /refund policy/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/within 30 days of charge/i)).toBeInTheDocument();
  });

  test("names Washington as governing jurisdiction", () => {
    renderPage(<Terms />);
    expect(screen.getByText(/State of Washington/)).toBeInTheDocument();
  });

  test("links back to /pricing", () => {
    renderPage(<Terms />);
    const link = screen.getByRole("link", { name: /pricing/i });
    expect(link.getAttribute("href")).toBe("/pricing");
  });
});
