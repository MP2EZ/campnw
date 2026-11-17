/** "PRO" pill next to the user menu; hidden unless the user is on Pro. */

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
