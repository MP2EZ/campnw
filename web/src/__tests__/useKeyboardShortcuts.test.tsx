import { describe, test, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";

function pressKey(key: string, opts: Partial<KeyboardEventInit> = {}) {
  const event = new KeyboardEvent("keydown", {
    key,
    bubbles: true,
    ...opts,
  });
  document.dispatchEvent(event);
}

describe("useKeyboardShortcuts", () => {
  test("calls handler when matching key is pressed", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardShortcuts([{ key: "j", handler, description: "Next" }]),
    );

    act(() => pressKey("j"));
    expect(handler).toHaveBeenCalledOnce();
  });

  test("ignores non-matching keys", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardShortcuts([{ key: "j", handler, description: "Next" }]),
    );

    act(() => pressKey("x"));
    expect(handler).not.toHaveBeenCalled();
  });

  test("ignores when focus is in input", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardShortcuts([{ key: "j", handler, description: "Next" }]),
    );

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    const event = new KeyboardEvent("keydown", { key: "j", bubbles: true });
    input.dispatchEvent(event);

    expect(handler).not.toHaveBeenCalled();
    document.body.removeChild(input);
  });

  test("ignores when focus is in textarea", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardShortcuts([{ key: "k", handler, description: "Prev" }]),
    );

    const textarea = document.createElement("textarea");
    document.body.appendChild(textarea);
    textarea.focus();

    const event = new KeyboardEvent("keydown", { key: "k", bubbles: true });
    textarea.dispatchEvent(event);

    expect(handler).not.toHaveBeenCalled();
    document.body.removeChild(textarea);
  });

  test("ignores when modifier key is held", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardShortcuts([{ key: "j", handler, description: "Next" }]),
    );

    act(() => pressKey("j", { ctrlKey: true }));
    expect(handler).not.toHaveBeenCalled();

    act(() => pressKey("j", { altKey: true }));
    expect(handler).not.toHaveBeenCalled();

    act(() => pressKey("j", { metaKey: true }));
    expect(handler).not.toHaveBeenCalled();
  });

  test("supports multiple shortcuts", () => {
    const handlerJ = vi.fn();
    const handlerK = vi.fn();
    renderHook(() =>
      useKeyboardShortcuts([
        { key: "j", handler: handlerJ, description: "Next" },
        { key: "k", handler: handlerK, description: "Prev" },
      ]),
    );

    act(() => pressKey("j"));
    act(() => pressKey("k"));

    expect(handlerJ).toHaveBeenCalledOnce();
    expect(handlerK).toHaveBeenCalledOnce();
  });
});
