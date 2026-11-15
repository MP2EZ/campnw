/**
 * Registry tags as words on a card (UX #16). Tags the fit line already
 * covers (RV, tent-only, walk-in) or the drive line does (boat-in) are left
 * out.
 */
const LABELS: Record<string, string> = {
  "old-growth": "Old-growth forest",
  "pull-through": "Pull-through sites",
  "group-sites": "Group sites",
  dispersed: "Dispersed camping",
  "boat-launch": "Boat launch",
  equestrian: "Horse camp",
  "pet-friendly": "Pets allowed",
  "kid-friendly": "Kid-friendly",
  accessible: "Accessible sites",
  campfire: "Campfires",
  shade: "Shaded sites",
};
const SAID_ELSEWHERE = new Set(["rv-friendly", "tent-only", "walk-in", "boat-in"]);

export function tagLabels(tags: string[]): string[] {
  return tags.filter((t) => !SAID_ELSEWHERE.has(t)).map((t) => {
    const words = t.replace(/-/g, " ");
    return LABELS[t] ?? words.charAt(0).toUpperCase() + words.slice(1);
  });
}
