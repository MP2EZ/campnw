/**
 * ProBadge — small "PRO" pill rendered next to the user menu when the
 * authenticated user is on Pro. Hidden for free users and anonymous
 * sessions. Linked to /pricing so clicking it lands on plan details.
 */

import { Link } from "react-router-dom";
import { useBilling } from "../hooks/useBilling";

export function ProBadge() {
  const { isPro } = useBilling();
  if (!isPro) return null;
  return (
    <Link to="/pricing" className="pro-badge" aria-label="Pro plan — view pricing">
      Pro
    </Link>
  );
}
