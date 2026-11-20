import { useEffect, useRef, useState } from "react";
import { EMAIL_NOT_CONFIRMED, useAuth } from "../hooks/useAuth";
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
  const { login, signup, resendConfirmation } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Set after a sign-up that needs email confirmation: the modal then shows
  // "check your email" instead of the form.
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent">("idle");

  useEffect(() => {
    if (open) return;
    setPendingEmail(null);
    setResendState("idle");
  }, [open]);

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
        const { needsConfirmation } = await signup(email, password, displayName);
        if (needsConfirmation) {
          setPendingEmail(email);
          setPassword("");
          return;
        }
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
        reason: message === EMAIL_NOT_CONFIRMED
          ? "email_not_confirmed"
          : /invalid|credential|password/i.test(message)
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

  const handleResend = async () => {
    if (!pendingEmail) return;
    setError(null);
    setResendState("sending");
    try {
      await resendConfirmation(pendingEmail);
      setResendState("sent");
    } catch (err) {
      setResendState("idle");
      setError(err instanceof Error ? err.message : "Couldn't resend the email");
    }
  };

  const backToSignIn = () => {
    setPendingEmail(null);
    setResendState("idle");
    setError(null);
    setMode("login");
  };

  if (!open) return null;

  const title = pendingEmail ? "Check your email" : mode === "login" ? "Sign in" : "Create account";

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
          <h2 id="auth-modal-title">{title}</h2>
          <button className="watch-close" onClick={onClose} ref={closeRef} aria-label="Close">
            &times;
          </button>
        </div>

        {pendingEmail ? (
          <div className="auth-form" data-testid="auth-check-email">
            {error && <p className="auth-error" role="alert">{error}</p>}
            <p>
              We sent a confirmation link to <strong>{pendingEmail}</strong>. Open it to
              finish creating your account, then sign in.
            </p>
            <button type="button" className="search-btn" onClick={backToSignIn}>
              Back to sign in
            </button>
            <p className="auth-switch" aria-live="polite">
              {resendState === "sent" ? (
                "Sent. It can take a minute to arrive."
              ) : (
                <>
                  No email?{" "}
                  <button
                    type="button"
                    className="auth-switch-btn"
                    onClick={handleResend}
                    disabled={resendState === "sending"}
                  >
                    Send it again
                  </button>
                </>
              )}
            </p>
          </div>
        ) : (
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
        )}
      </div>
    </div>
  );
}
