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

export const WatchContext = createContext<OpenWatch | null>(null);

/** Null outside ResultsPage: callers render the stub instead. */
export const useOpenWatch = () => useContext(WatchContext);
