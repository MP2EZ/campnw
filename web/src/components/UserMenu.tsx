import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useBilling } from "../hooks/useBilling";
import { deleteAccount, exportData } from "../api";

export function UserMenu() {
  const { user, logout, updateProfile } = useAuth();
  const { isPro, status, openPortal, startCheckout } = useBilling();
  const [open, setOpen] = useState(false);
  const [showPrefs, setShowPrefs] = useState(false);
  const [showBilling, setShowBilling] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [billingActionPending, setBillingActionPending] = useState(false);
  const [billingError, setBillingError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
        setShowPrefs(false);
        setShowBilling(false);
        setShowDeleteConfirm(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  if (!user) return null;

  const displayLabel = user.display_name || user.email.split("@")[0];

  const handleExport = async () => {
    const data = await exportData();
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "campable-data.json";
    a.click();
    URL.revokeObjectURL(url);
    setOpen(false);
  };

  const handleDelete = async () => {
    await deleteAccount();
    await logout();
    setOpen(false);
  };

  return (
    <div className="user-menu" ref={menuRef}>
      <button
        className="header-btn user-menu-trigger"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {displayLabel}
      </button>

      {open && (
        <div className="user-menu-dropdown">
          {!showPrefs && !showBilling && !showDeleteConfirm && (
            <>
              <button
                className="user-menu-item"
                onClick={() => setShowPrefs(true)}
              >
                Preferences
              </button>
              <button
                className="user-menu-item"
                onClick={() => {
                  setShowBilling(true);
                  setBillingError(null);
                }}
              >
                Billing
                {isPro && <span className="pro-badge">Pro</span>}
              </button>
              <button className="user-menu-item" onClick={handleExport}>
                Export data
              </button>
              <button
                className="user-menu-item"
                onClick={() => setShowDeleteConfirm(true)}
              >
                Delete account
              </button>
              <hr className="user-menu-divider" />
              <button
                className="user-menu-item"
                onClick={async () => {
                  await logout();
                  setOpen(false);
                }}
              >
                Sign out
              </button>
            </>
          )}

          {showBilling && (
            <div className="billing-status">
              <div className="billing-status-row">
                <span className="label">Plan</span>
                <strong>{isPro ? "Pro ($5/mo)" : "Free"}</strong>
              </div>
              {status?.subscription_expires_at && (
                <p className="billing-expires-note">
                  Pro until{" "}
                  {new Date(status.subscription_expires_at).toLocaleDateString()}
                </p>
              )}
              {billingError && (
                <p className="auth-error" role="alert">{billingError}</p>
              )}
              <hr className="user-menu-divider" />
              {isPro ? (
                <button
                  className="user-menu-item"
                  disabled={billingActionPending}
                  onClick={async () => {
                    setBillingActionPending(true);
                    setBillingError(null);
                    try {
                      await openPortal();
                    } catch (e) {
                      setBillingError(
                        e instanceof Error ? e.message : "Portal unavailable"
                      );
                      setBillingActionPending(false);
                    }
                  }}
                >
                  {billingActionPending ? "Opening…" : "Manage billing"}
                </button>
              ) : status?.configured ? (
                <button
                  className="user-menu-item"
                  disabled={billingActionPending}
                  onClick={async () => {
                    setBillingActionPending(true);
                    setBillingError(null);
                    try {
                      await startCheckout();
                    } catch (e) {
                      setBillingError(
                        e instanceof Error ? e.message : "Checkout unavailable"
                      );
                      setBillingActionPending(false);
                    }
                  }}
                >
                  {billingActionPending ? "Opening Stripe…" : "Upgrade to Pro"}
                </button>
              ) : (
                <Link
                  to="/pricing"
                  className="user-menu-item"
                  onClick={() => setOpen(false)}
                >
                  See pricing
                </Link>
              )}
              <button
                className="user-menu-item"
                onClick={() => setShowBilling(false)}
              >
                Back
              </button>
            </div>
          )}

          {showPrefs && (
            <PreferencesForm
              user={user}
              onSave={async (updates) => {
                await updateProfile(updates);
                setShowPrefs(false);
              }}
              onCancel={() => setShowPrefs(false)}
            />
          )}

          {showDeleteConfirm && (
            <div className="user-menu-confirm">
              <p>Delete your account and all data? This cannot be undone.</p>
              <div className="user-menu-confirm-actions">
                <button
                  className="user-menu-item danger"
                  onClick={handleDelete}
                >
                  Delete
                </button>
                <button
                  className="user-menu-item"
                  onClick={() => setShowDeleteConfirm(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PreferencesForm({
  user,
  onSave,
  onCancel,
}: {
  user: { display_name: string; home_base: string; default_state: string; default_nights: number; recommendations_enabled?: boolean };
  onSave: (updates: Record<string, string | number | boolean>) => Promise<void>;
  onCancel: () => void;
}) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [homeBase, setHomeBase] = useState(user.home_base);
  const [defaultState, setDefaultState] = useState(user.default_state);
  const [defaultNights, setDefaultNights] = useState(user.default_nights);
  const [recsEnabled, setRecsEnabled] = useState(user.recommendations_enabled ?? false);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    await onSave({
      display_name: displayName,
      home_base: homeBase,
      default_state: defaultState,
      default_nights: defaultNights,
      recommendations_enabled: recsEnabled,
    });
    setSaving(false);
  };

  return (
    <form onSubmit={handleSubmit} className="prefs-form">
      <label>
        Name
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          maxLength={100}
        />
      </label>
      <label>
        Home base
        <input
          type="text"
          value={homeBase}
          onChange={(e) => setHomeBase(e.target.value)}
          placeholder="e.g. Seattle, WA"
          maxLength={200}
        />
      </label>
      <label>
        Default state
        <select
          value={defaultState}
          onChange={(e) => setDefaultState(e.target.value)}
        >
          <option value="">All</option>
          <option value="WA">WA</option>
          <option value="OR">OR</option>
          <option value="ID">ID</option>
        </select>
      </label>
      <label>
        Default nights
        <input
          type="number"
          value={defaultNights}
          onChange={(e) => setDefaultNights(Number(e.target.value))}
          min={1}
          max={14}
        />
      </label>
      <label className="prefs-toggle">
        <span>Personalized recommendations</span>
        <input
          type="checkbox"
          checked={recsEnabled}
          onChange={(e) => setRecsEnabled(e.target.checked)}
        />
        <span className="toggle-track" />
      </label>
      <div className="prefs-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "..." : "Save"}
        </button>
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
