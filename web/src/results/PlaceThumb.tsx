import { useState } from "react";
import type { CampgroundResult } from "../api";

/*
 * The design's 112px tiles, for places without a photo (all of WA so far).
 * Decorative art, so the fills are the illustration's own palette rather
 * than theme tokens; results.css dims them a little in dark mode.
 */
const TILES = {
  island: (
    <><rect width="112" height="112" fill="#dbe8ea" /><rect y="52" width="112" height="60" fill="#9fc4cf" />
      <path d="M30 62 Q56 34 84 62 Z" fill="#9db58a" /><path d="M46 52 L52 36 L58 52 Z" fill="#2d5016" />
      <path d="M56 54 L63 40 L70 54 Z" fill="#3d6b24" /><path d="M14 92 L30 92 L26 98 L18 98 Z" fill="#b4561a" /></>
  ),
  sea: (
    <><rect width="112" height="112" fill="#dbe8ea" /><circle cx="80" cy="34" r="12" fill="#efc28c" />
      <path d="M0 60 L16 46 L28 54 L42 40 L58 60 Z" fill="#9db58a" /><rect y="60" width="112" height="52" fill="#9fc4cf" />
      <path d="M12 76 Q22 71 32 76 T52 76" stroke="#fffdf8" strokeWidth="2" fill="none" strokeLinecap="round" />
      <path d="M0 102 Q56 94 112 100 L112 112 L0 112 Z" fill="#e8dbbd" /></>
  ),
  lake: (
    <><rect width="112" height="112" fill="#e4ecdc" /><path d="M0 64 L30 32 L48 50 L72 22 L112 64 Z" fill="#b6c7a7" />
      <rect y="64" width="112" height="48" fill="#a8cad2" /><path d="M14 66 L23 40 L32 66 Z" fill="#2d5016" />
      <path d="M40 82 H72" stroke="#fffdf8" strokeWidth="2" strokeLinecap="round" /></>
  ),
  river: (
    <><rect width="112" height="112" fill="#e2e9d6" />
      <path d="M44 -4 C 30 30, 84 48, 62 80 S 48 108, 58 118" stroke="#9fc4cf" strokeWidth="20" fill="none" strokeLinecap="round" />
      <path d="M10 52 L18 30 L26 52 Z" fill="#2d5016" /><path d="M80 100 L89 76 L98 100 Z" fill="#2d5016" />
      <path d="M90 60 L97 42 L104 60 Z" fill="#5e8a3f" /></>
  ),
  forest: (
    <><rect width="112" height="112" fill="#dde6d1" /><path d="M0 112 L0 86 Q56 70 112 86 L112 112 Z" fill="#c4d3b2" />
      <path d="M20 94 L36 38 L52 94 Z" fill="#2d5016" /><path d="M48 98 L66 26 L84 98 Z" fill="#3d6b24" />
      <path d="M78 96 L91 54 L104 96 Z" fill="#5e8a3f" /></>
  ),
};

function tile(r: CampgroundResult): keyof typeof TILES {
  const tags = r.tags ?? [];
  if (r.boat_in) return "island";
  if (tags.includes("beach")) return "sea";
  if (tags.includes("lakeside")) return "lake";
  if (tags.includes("riverside")) return "river";
  return "forest";
}

/** The place's first photo, or a tile drawn from its tags. */
export function PlaceThumb({ result }: { result: CampgroundResult }) {
  const [failed, setFailed] = useState(false);
  const photo = result.image_urls?.[0];
  return (
    <div className="rv2-thumb">
      {photo && !failed ? (
        <img src={photo} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : (
        <svg viewBox="0 0 112 112" aria-hidden="true">{TILES[tile(result)]}</svg>
      )}
    </div>
  );
}
