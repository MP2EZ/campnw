import { createContext, useContext } from "react";
import type { CampgroundResult } from "../api";
import type { WatchFrom } from "./WatchSheet";

export type SheetMode = "watch" | "remind";

/**
 * Opens the Watch sheet for a place, on one stay (its first night) or the
 * first: a watch for full stays, or a release reminder ("remind").
 */
export type OpenWatch = (
  place: CampgroundResult, initial: string | undefined, from: WatchFrom, mode?: SheetMode,
) => void;

/** Provided by ResultsPage; everything that opens the sheet renders inside it. */
export const WatchContext = createContext<OpenWatch | null>(null);

export function useOpenWatch(): OpenWatch {
  const open = useContext(WatchContext);
  if (!open) throw new Error("useOpenWatch needs a WatchContext.Provider");
  return open;
}
