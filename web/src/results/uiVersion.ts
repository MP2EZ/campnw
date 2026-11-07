import { useEffect, useState } from "react";
import { getPosthog } from "../api";

/**
 * Which results page to show (v1.48 decision D1). Order of precedence:
 * `?ui=v2` / `?ui=v1` (remembered per browser), then the `results_v2` PostHog
 * flag, then v1. `?ui=auto` forgets the override and goes back to the flag.
 */
export type UiVersion = "v1" | "v2";

export const UI_STORAGE_KEY = "campable-ui";
const FLAG = "results_v2";

const isVersion = (v: string | null): v is UiVersion => v === "v1" || v === "v2";

/**
 * The per-browser override, if any. `store`: the value to save, `null` to
 * clear it, undefined to leave storage alone.
 */
export function uiOverride(
  search: string,
  stored: string | null,
): { override: UiVersion | null; store?: UiVersion | null } {
  const param = new URLSearchParams(search).get("ui");
  if (isVersion(param)) return { override: param, store: param };
  if (param === "auto") return { override: null, store: null };
  return { override: isVersion(stored) ? stored : null };
}

export function resolveUiVersion(search: string, stored: string | null, flag: boolean | undefined) {
  const { override, store } = uiOverride(search, stored);
  return { version: override ?? (flag === true ? "v2" : "v1"), store };
}

function readStored(): string | null {
  try {
    return localStorage.getItem(UI_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(value: UiVersion | null) {
  try {
    if (value) localStorage.setItem(UI_STORAGE_KEY, value);
    else localStorage.removeItem(UI_STORAGE_KEY);
  } catch {
    // Private mode or blocked storage: the override lasts for this page only.
  }
}

// The snippet's stub returns undefined until posthog-js and its flags load.
const readFlag = () => getPosthog()?.isFeatureEnabled?.(FLAG);

export function useUiVersion(): UiVersion {
  const [{ override, store }] = useState(() => uiOverride(window.location.search, readStored()));
  const [flag, setFlag] = useState(readFlag);
  const version: UiVersion = override ?? (flag === true ? "v2" : "v1");

  useEffect(() => {
    if (store !== undefined) writeStored(store);
  }, [store]);

  useEffect(() => {
    if (override) return;
    const off = getPosthog()?.onFeatureFlags?.(() => setFlag(readFlag()));
    return typeof off === "function" ? off : undefined;
  }, [override]);

  useEffect(() => {
    getPosthog()?.register({ ui_version: version });
    document.documentElement.dataset.ui = version;
  }, [version]);

  return version;
}
