import { describe, test, expect, vi } from "vitest";
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

  test.each([
    ["input", "j"],
    ["textarea", "k"],
  ])("ignores when focus is in %s", (tag, key) => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardShortcuts([{ key, handler, description: "Shortcut" }]),
    );

    const field = document.createElement(tag);
    document.body.appendChild(field);
    field.focus();

    field.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));

    expect(handler).not.toHaveBeenCalled();
    document.body.removeChild(field);
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
