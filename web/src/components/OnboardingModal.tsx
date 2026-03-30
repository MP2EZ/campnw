import { useEffect, useRef, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { track } from "../api";

const TAG_OPTIONS = [
  "lakeside", "riverside", "beach", "old-growth", "forest", "alpine",
  "rv-friendly", "tent-only", "walk-in", "trails", "swimming", "fishing",
  "boating", "pet-friendly", "kid-friendly", "accessible", "campfire",
  "remote", "hot-springs", "waterfall",
];

export function OnboardingModal({ onClose }: { onClose: () => void }) {
  const { updateProfile } = useAuth();
  const [step, setStep] = useState(1);
  const [homeBase, setHomeBase] = useState("");
  const modalRef = useRef<HTMLDivElement>(null);

  // Focus trap + Escape to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && modalRef.current) {
        const focusable = modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) {
        next.delete(tag);
      } else if (next.size < 5) {
        next.add(tag);
      }
      return next;
    });
  };

  const handleStep1 = async () => {
    if (homeBase.trim()) {
      await updateProfile({ home_base: homeBase.trim() });
    }
    setStep(2);
  };

  const handleStep2 = async () => {
    setSaving(true);
    await updateProfile({
      preferred_tags: Array.from(selectedTags),
      onboarding_complete: true,
    });
    track("onboarding_completed", { tags_selected: selectedTags.size });
    setSaving(false);
    onClose();
  };

  const handleSkip = async () => {
    await updateProfile({ onboarding_complete: true });
    track("onboarding_skipped", { step });
    onClose();
  };

  return (
    <div className="watch-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Welcome setup">
      <div className="onboarding-modal" ref={modalRef} onClick={(e) => e.stopPropagation()}>
        <div className="onboarding-header">
          <h2>Welcome to campable</h2>
          <p className="onboarding-subtitle">
            {step === 1
              ? "Set your home base for drive time estimates"
              : "Pick your favorite camping styles (up to 5)"}
          </p>
          <span className="onboarding-step">Step {step} of 2</span>
        </div>

        {step === 1 ? (
          <div className="onboarding-body">
            <label htmlFor="onboarding-home" className="onboarding-label">
              Home base city
            </label>
            <input
              id="onboarding-home"
              type="text"
              value={homeBase}
              onChange={(e) => setHomeBase(e.target.value)}
              placeholder="e.g. Seattle, WA"
              maxLength={200}
              className="onboarding-input"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleStep1()}
            />
            <div className="onboarding-actions">
              <button className="btn-secondary" onClick={handleSkip}>
                Skip
              </button>
              <button className="btn-primary" onClick={handleStep1}>
                Next
              </button>
            </div>
          </div>
        ) : (
          <div className="onboarding-body">
            <div className="onboarding-tags" role="group" aria-label="Preferred tags">
              {TAG_OPTIONS.map((tag) => (
                <button
                  key={tag}
                  className={`onboarding-tag${selectedTags.has(tag) ? " selected" : ""}`}
                  onClick={() => toggleTag(tag)}
                  aria-pressed={selectedTags.has(tag)}
                  type="button"
                >
                  {tag}
                </button>
              ))}
            </div>
            <p className="onboarding-tag-count">
              {selectedTags.size}/5 selected
            </p>
            <div className="onboarding-actions">
              <button className="btn-secondary" onClick={handleSkip}>
                Skip
              </button>
              <button
                className="btn-primary"
                onClick={handleStep2}
                disabled={saving}
              >
                {saving ? "Saving..." : "Done"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
