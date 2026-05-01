import { describe, test, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ErrorBoundary } from "../components/ErrorBoundary";

vi.mock("posthog-js", () => ({
  default: {
    captureException: vi.fn(),
  },
}));

import posthog from "posthog-js";

function ThrowingChild() {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  test("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <p>Hello</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  test("renders fallback UI when child throws", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    );

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText(/unexpected error/)).toBeInTheDocument();
    expect(screen.getByText("Reload")).toBeInTheDocument();

    spy.mockRestore();
  });

  test("forwards caught errors to PostHog with componentStack", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const captureException = vi.mocked(posthog).captureException;
    captureException.mockClear();

    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    );

    // Dynamic import resolves on a microtask — wait for it
    await waitFor(() => {
      expect(captureException).toHaveBeenCalledTimes(1);
    });

    const [error, props] = captureException.mock.calls[0];
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe("boom");
    expect(props).toMatchObject({ componentStack: expect.any(String) });

    spy.mockRestore();
  });
});
