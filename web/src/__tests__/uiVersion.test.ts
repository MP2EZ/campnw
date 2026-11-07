import { describe, test, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { resolveUiVersion, useUiVersion, UI_STORAGE_KEY } from "../results/uiVersion";

describe("resolveUiVersion", () => {
  test.each<[string, string, string | null, boolean | undefined, string, string | null | undefined]>([
    ["defaults to v1", "", null, undefined, "v1", undefined],
    ["follows the PostHog flag", "", null, true, "v2", undefined],
    ["flag off is v1", "", null, false, "v1", undefined],
    ["?ui=v2 wins over the flag and is stored", "?ui=v2", null, false, "v2", "v2"],
    ["?ui=v1 wins over the flag and is stored", "?ui=v1", "v2", true, "v1", "v1"],
    ["a stored override wins over the flag", "", "v1", true, "v1", undefined],
    ["?ui=auto clears the override", "?ui=auto", "v2", false, "v1", null],
    ["unknown values are ignored", "?ui=v3", "nope", true, "v2", undefined],
  ])("%s", (_label, search, stored, flag, version, store) => {
    expect(resolveUiVersion(search, stored, flag)).toEqual({ version, store });
  });
});

describe("useUiVersion", () => {
  const register = vi.fn();
  let flagsListener: (() => void) | undefined;
  let flag = false;

  beforeEach(() => {
    localStorage.clear();
    register.mockClear();
    flag = false;
    (window as unknown as { posthog: unknown }).posthog = {
      register,
      isFeatureEnabled: (key: string) => key === "results_v2" && flag,
      onFeatureFlags: (cb: () => void) => {
        flagsListener = cb;
        return () => { flagsListener = undefined; };
      },
    };
  });

  afterEach(() => {
    delete (window as unknown as { posthog?: unknown }).posthog;
    window.history.replaceState({}, "", "/");
  });

  test("registers ui_version and switches when flags arrive", () => {
    const { result } = renderHook(() => useUiVersion());
    expect(result.current).toBe("v1");
    expect(register).toHaveBeenLastCalledWith({ ui_version: "v1" });

    flag = true;
    act(() => flagsListener?.());
    expect(result.current).toBe("v2");
    expect(register).toHaveBeenLastCalledWith({ ui_version: "v2" });
  });

  test("a URL override persists and ignores the flag", () => {
    window.history.replaceState({}, "", "/?ui=v2");
    const { result } = renderHook(() => useUiVersion());
    expect(result.current).toBe("v2");
    expect(localStorage.getItem(UI_STORAGE_KEY)).toBe("v2");
  });

  test("survives storage that throws", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    flag = true;
    const { result } = renderHook(() => useUiVersion());
    expect(result.current).toBe("v2");
    spy.mockRestore();
  });
});
