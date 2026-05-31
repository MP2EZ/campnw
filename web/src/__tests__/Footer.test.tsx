import { describe, test, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Footer } from "../components/Footer";

function renderFooter() {
  return render(
    <MemoryRouter>
      <Footer />
    </MemoryRouter>,
  );
}

describe("Footer", () => {
  test("renders the contentinfo landmark", () => {
    renderFooter();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });

  test("renders all expected nav links", () => {
    renderFooter();
    const nav = screen.getByRole("navigation", { name: /footer/i });
    const links = within(nav).getAllByRole("link");
    const hrefs = links.map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(
      expect.arrayContaining([
        "/about",
        "/pricing",
        "/privacy",
        "/terms",
        "mailto:hello@palouselabs.com",
      ]),
    );
  });

  test("renders the current year in the meta line", () => {
    renderFooter();
    const year = new Date().getFullYear().toString();
    expect(screen.getByText(new RegExp(`${year} Campable`))).toBeInTheDocument();
  });
});
