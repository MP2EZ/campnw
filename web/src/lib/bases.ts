/** Home bases the search form offers; anything else came from the NL parser or a profile. */
export const DRIVE_FROM: ReadonlyArray<[key: string, label: string]> = [
  ["seattle", "Seattle"], ["bellevue", "Bellevue"], ["portland", "Portland"],
  ["spokane", "Spokane"], ["bellingham", "Bellingham"], ["bend", "Bend, OR"],
  ["bozeman", "Bozeman, MT"], ["missoula", "Missoula, MT"], ["jackson", "Jackson, WY"],
  ["sacramento", "Sacramento, CA"], ["reno", "Reno, NV"], ["moscow", "Moscow, ID"],
];

export const KNOWN_BASE_KEYS: readonly string[] = DRIVE_FROM.map(([key]) => key);
