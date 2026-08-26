/**
 * Display labels for BookingSystem values.
 *
 * Lives in lib/ rather than beside ResultCard so pages can import it without
 * pulling ResultCard (and everything it imports) into their chunk. It was
 * previously exported from ResultCard and re-declared inline twice in MapView
 * plus expressed as a nested ternary in ItineraryCard — and that ternary had
 * already drifted, silently labelling id_state campgrounds "Rec.gov".
 */
export const SOURCE_LABELS: Record<string, string> = {
  recgov: "Rec.gov",
  wa_state: "WA Parks",
  or_state: "OR Parks",
  id_state: "ID Parks",
};

/** Label for a booking system, falling back to the raw value. */
export function sourceLabel(bookingSystem: string): string {
  return SOURCE_LABELS[bookingSystem] || bookingSystem;
}
