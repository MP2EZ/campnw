import { createContext, useContext } from "react";
import type { CampgroundResult, SearchResponse, SearchParams } from "../api";

export interface SearchContextValue {
  results: SearchResponse | null;
  loading: boolean;
  searchDates: { start: string; end: string } | null;
  searchParams: SearchParams | null;
  sourceFilter: Set<string>;
  filteredResults: CampgroundResult[];
}

export const SearchContext = createContext<SearchContextValue | null>(null);

export function useSearchContext(): SearchContextValue {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error("useSearchContext must be used within SearchContext.Provider");
  return ctx;
}
