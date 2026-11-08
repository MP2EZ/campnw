import { createContext, useContext, useSyncExternalStore } from "react";

export type SelectionSource = "list" | "map";

export interface Selection {
  id: string | null;
  /** "list": a card is hovered or focused. "map": a pin was chosen. */
  from: SelectionSource | null;
}

export interface SelectionStore {
  get(): Selection;
  select(id: string, from: SelectionSource): void;
  /** A card lost hover or focus: clear its list selection, if still current. */
  release(id: string): void;
  subscribe(cb: () => void): () => void;
}

const NONE: Selection = { id: null, from: null };

/**
 * The place selected across the v2 list and map (D13). A store rather than
 * React state, so hovering a card re-renders that card and the map, not the
 * whole list.
 */
export function createSelectionStore(): SelectionStore {
  let current = NONE;
  const subs = new Set<() => void>();
  const set = (next: Selection) => {
    if (next.id === current.id && next.from === current.from) return;
    current = next;
    subs.forEach((cb) => cb());
  };
  return {
    get: () => current,
    select: (id, from) => {
      // Moving focus to the card a pin chose mustn't undo the pin's choice.
      if (from === "list" && current.id === id && current.from === "map") return;
      set({ id, from });
    },
    release: (id) => {
      if (current.id === id && current.from === "list") set(NONE);
    },
    subscribe: (cb) => {
      subs.add(cb);
      return () => { subs.delete(cb); };
    },
  };
}

export const SelectionContext = createContext<SelectionStore | null>(null);

const noop = () => () => {};

/**
 * Props that make a card part of the selection: hover or focus selects it
 * for the map, and it is marked when its pin was chosen. Inert outside a
 * SelectionContext.
 */
export function useCardSelection(id: string) {
  const store = useContext(SelectionContext);
  const fromMap = useSyncExternalStore(store?.subscribe ?? noop,
    () => store?.get().id === id && store.get().from === "map");
  if (!store) return { selected: false };
  return {
    selected: fromMap,
    onMouseEnter: () => store.select(id, "list"),
    onMouseLeave: () => store.release(id),
    onFocus: () => store.select(id, "list"),
    onBlur: (e: React.FocusEvent) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) store.release(id);
    },
  };
}
