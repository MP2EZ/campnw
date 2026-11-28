import { useEffect } from "react";
import { isNativePush, nativePermission, registerNativePush } from "../lib/nativePush";

/** In the iOS app, (re-)register this phone whenever someone signs in with
 * notifications already allowed. That moves a shared phone to the account
 * now using it, and picks up a token iOS rotated. */
export function useNativePushSync(userId: number | null | undefined): void {
  useEffect(() => {
    if (!userId || !isNativePush()) return;
    let cancelled = false;
    nativePermission()
      .then((p) => (p === "granted" && !cancelled ? registerNativePush() : undefined))
      .catch(() => {
        // Retried on the next launch or sign-in.
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);
}
