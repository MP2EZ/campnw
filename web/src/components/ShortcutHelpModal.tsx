import { useEffect, useRef } from "react";

const SHORTCUTS = [
  { key: "j", description: "Next result" },
  { key: "k", description: "Previous result" },
  { key: "w", description: "Open watchlist" },
  { key: "m", description: "Toggle map / list view" },
  { key: "?", description: "Show this help" },
  { key: "Esc", description: "Close overlay" },
];

export function ShortcutHelpModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open && closeRef.current) closeRef.current.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
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
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="watch-overlay" onClick={onClose}>
      <div
        className="watch-panel shortcut-modal"
        onClick={(e) => e.stopPropagation()}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
      >
        <div className="watch-panel-header">
          <h2>Keyboard shortcuts</h2>
          <button className="watch-close" onClick={onClose} ref={closeRef} aria-label="Close">
            &times;
          </button>
        </div>
        <dl className="shortcut-list">
          {SHORTCUTS.map((s) => (
            <div key={s.key} className="shortcut-row">
              <dt><kbd>{s.key}</kbd></dt>
              <dd>{s.description}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
