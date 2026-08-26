import { describe, test, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ErrorBoundary } from "../components/ErrorBoundary";

// Assert against the snippet-initialized instance the app actually uses
// (see getPosthog in api.ts), not the npm module singleton — calls on that
// one silently no-op, so mocking it proved nothing.
const mockPosthog = vi.hoisted(() => ({
  captureException: vi.fn(),
  capture: vi.fn(),
}));

vi.mock("../api", () => ({
  getPosthog: vi.fn(() => mockPosthog),
}));

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
    mockPosthog.captureException.mockClear();
    mockPosthog.capture.mockClear();

    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    );

    await waitFor(() => {
      expect(mockPosthog.captureException).toHaveBeenCalledTimes(1);
    });

    const [error, props] = mockPosthog.captureException.mock.calls[0];
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe("boom");
    expect(props).toMatchObject({ componentStack: expect.any(String) });

    // Crash rate needs to be queryable as an event, not only as an exception feed
    expect(mockPosthog.capture).toHaveBeenCalledWith(
      "app_crashed",
      expect.objectContaining({ error_name: "Error", error_message: "boom" }),
    );

    spy.mockRestore();
  });
});
