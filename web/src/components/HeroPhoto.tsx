import { useState } from "react";
import { track } from "../api";

interface HeroPhotoProps {
  urls: string[];
  name: string;
  attribution: string;
  facilityId: string;
  source: string;
}

export function HeroPhoto({
  urls,
  name,
  attribution,
  facilityId,
  source,
}: HeroPhotoProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [failedUrls, setFailedUrls] = useState<Set<string>>(() => new Set());
  const hasPager = urls.length > 1;
  const alt = `Photo of ${name}`;

  const goTo = (i: number, via: "dot" | "arrow") => {
    if (i === activeIndex) return;
    setActiveIndex(i);
    track("card_photo_paged", {
      facility_id: facilityId,
      source,
      index: i,
      total: urls.length,
      via,
    });
  };

  const goRel = (delta: number) => {
    const next = (activeIndex + delta + urls.length) % urls.length;
    goTo(next, "arrow");
  };

  const handleImageError = (url: string, index: number) => {
    if (failedUrls.has(url)) return;
    setFailedUrls((prev) => new Set(prev).add(url));
    track("photo_load_failed", {
      facility_id: facilityId,
      source,
      // Truncate to query-stripped, max 200 chars — forward-safe in case
      // RIDB or RA ever return signed/tokenized URLs we don't want in
      // analytics logs.
      url: url.split("?")[0].slice(0, 200),
      index,
      total: urls.length,
    });
  };

  return (
    <div className="hero is-photo">
      <img
        src={urls[activeIndex]}
        alt={alt}
        loading="lazy"
        decoding="async"
        width={600}
        height={338}
        referrerPolicy="no-referrer"
        onError={() => handleImageError(urls[activeIndex], activeIndex)}
      />
      {hasPager && (
        <>
          <button
            type="button"
            className="hero-arrow hero-arrow-prev"
            aria-label="Previous photo"
            onClick={() => goRel(-1)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" width="20" height="20">
              <path
                d="M15 6l-6 6 6 6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <button
            type="button"
            className="hero-arrow hero-arrow-next"
            aria-label="Next photo"
            onClick={() => goRel(1)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" width="20" height="20">
              <path
                d="M9 6l6 6-6 6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <div
            className="hero-pager"
            role="group"
            aria-label={`Photo ${activeIndex + 1} of ${urls.length}`}
          >
            {urls.map((_, i) => (
              <button
                key={i}
                type="button"
                aria-current={i === activeIndex ? "true" : undefined}
                aria-label={`Show photo ${i + 1} of ${urls.length}`}
                className={`hero-dot${i === activeIndex ? " active" : ""}`}
                onClick={() => goTo(i, "dot")}
              />
            ))}
          </div>
        </>
      )}
      {attribution && (
        <div className="hero-attribution">Photo: {attribution}</div>
      )}
      {/* Visually hidden status region for screen readers when paging. */}
      {hasPager && (
        <div className="visually-hidden" aria-live="polite" aria-atomic="true">
          Photo {activeIndex + 1} of {urls.length}
        </div>
      )}
    </div>
  );
}
