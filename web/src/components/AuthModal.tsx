import { useEffect, useRef, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { track } from "../api";

export function AuthModal({
  open,
  entryPoint = "unknown",
  onClose,
}: {
  open: boolean;
  entryPoint?: string;
  onClose: () => void;
}) {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // The modal had zero track() calls, so the landing -> signup funnel had
  // exactly one step: the success event. No open, no mode toggle, no submit
  // attempt, and — the classic silent funnel killer — no failure.
  useEffect(() => {
    if (open) track("auth_modal_opened", { entry_point: entryPoint, mode });
    // Only on open; a mode toggle emits its own event below.
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    track("auth_submitted", { mode, entry_point: entryPoint });
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(email, password, displayName);
      }
      setEmail("");
      setPassword("");
      setDisplayName("");
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      // Normalised, never the raw Supabase string — and never the email.
      track("auth_failed", {
        mode,
        entry_point: entryPoint,
        reason: /invalid|credential|password/i.test(message)
          ? "invalid_credentials"
          : /exists|registered/i.test(message)
            ? "already_registered"
            : /network|fetch/i.test(message)
              ? "network"
              : "other",
      });
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="watch-overlay" onClick={onClose}>
      <div
        className="watch-panel auth-modal"
        onClick={(e) => e.stopPropagation()}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
      >
        <div className="watch-panel-header">
          <h2 id="auth-modal-title">
            {mode === "login" ? "Sign in" : "Create account"}
          </h2>
          <button className="watch-close" onClick={onClose} ref={closeRef} aria-label="Close">
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <p className="auth-error" role="alert">{error}</p>}

          {mode === "signup" && (
            <label>
              Name
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Optional"
                maxLength={100}
                autoComplete="name"
                data-testid="display-name-input"
              />
            </label>
          )}

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              data-testid="email-input"
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              data-testid="password-input"
            />
          </label>

          <button type="submit" className="search-btn" disabled={submitting}>
            {submitting
              ? "..."
              : mode === "login"
                ? "Sign in"
                : "Create account"}
          </button>

          <p className="auth-switch">
            {mode === "login" ? (
              <>
                No account?{" "}
                <button
                  type="button"
                  className="auth-switch-btn"
                  onClick={() => {
                    track("auth_mode_toggled", { to: "signup", entry_point: entryPoint });
                    setMode("signup");
                    setError(null);
                  }}
                >
                  Create one
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  type="button"
                  className="auth-switch-btn"
                  onClick={() => {
                    track("auth_mode_toggled", { to: "login", entry_point: entryPoint });
                    setMode("login");
                    setError(null);
                  }}
                >
                  Sign in
                </button>
              </>
            )}
          </p>
        </form>
      </div>
    </div>
  );
}
