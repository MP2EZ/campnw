/**
 * Names as people write them (UX #17). Recreation.gov sends many names in
 * ALL CAPS ("OHANAPECOSH CAMPGROUND", "Loop ELEC"); those are title-cased for
 * display. Names with any lower case are left as their source wrote them.
 */
const KEEP = new Set([
  "RV", "NF", "NFS", "FS", "NRA", "SRA", "NP", "SP", "USFS", "BLM", "KOA", "OHV", "ATV", "ADA", "CCC", "YMCA",
  "US", "USA", "WA", "OR", "ID", "MT", "WY", "CA", "NV", "UT",
]);
const SMALL = new Set(["of", "the", "and", "at", "on", "in", "by", "to", "for"]);
const ROMAN = /^(?=[IVX]{2,})X{0,3}(IX|IV|V?I{0,3})$/;

function word(w: string, first: boolean): string {
  if (KEEP.has(w) || ROMAN.test(w) || /^[A-Z]$/.test(w)) return w;
  const lower = w.toLowerCase();
  if (!first && SMALL.has(lower)) return lower;
  if (/^MC[A-Z]{2,}$/.test(w)) return `Mc${w[2]}${lower.slice(3)}`;
  if (/^O'[A-Z]/.test(w)) return `O'${w[2]}${lower.slice(3)}`;
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

export function displayName(name: string): string {
  if (/[a-z]/.test(name) || !/[A-Z]/.test(name)) return name;
  let first = true;
  return name.replace(/[A-Z0-9'.]+/g, (w, at: number) => {
    // A word after a hyphen ("BOAT-IN") counts as mid-name; after "(" or " - " as a start.
    const out = word(w, first || /[(]\s*$/.test(name.slice(0, at)));
    first = false;
    return out;
  });
}
