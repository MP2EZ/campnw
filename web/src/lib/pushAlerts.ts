// Taps on native watch alerts. The listener is attached before React mounts
// so a tap that cold-starts the app isn't lost; the alert waits here until
// the app shell reads it.
import { useSyncExternalStore } from "react";
import { PushNotifications } from "@capacitor/push-notifications";
import { isNativePush } from "./nativePush";
import { track } from "../api";

export interface PushAlert {
  watchId: number;
  title: string;
  body: string;
  bookingUrl: string;
}

const PROVIDERS: [string, string][] = [
  ["recreation.gov", "Recreation.gov"],
  ["goingtocamp.com", "WA State Parks"],
  ["reserveamerica.com", "ReserveAmerica"],
];

export function providerLabel(url: string): string {
  try {
    const host = new URL(url).hostname;
    const hit = PROVIDERS.find(([domain]) => host === domain || host.endsWith(`.${domain}`));
    return hit ? hit[1] : host;
  } catch {
    return "the booking site";
  }
}

let pending: PushAlert | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

/** Read an alert from the notification's data. Only https booking links are
 * kept: the sheet opens this URL outside the app. */
export function parsePushAlert(data: unknown, title = "", body = ""): PushAlert | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  const watchId = Number(d.watch_id);
  const url = typeof d.booking_url === "string" ? d.booking_url : "";
  if (!Number.isInteger(watchId) || watchId <= 0) return null;
  let bookingUrl = "";
  try {
    if (new URL(url).protocol === "https:") bookingUrl = url;
  } catch {
    // not a URL
  }
  if (!bookingUrl) return null;
  const aps = (d.aps ?? {}) as { alert?: { title?: unknown; body?: unknown } };
  const alert = aps.alert ?? {};
  return {
    watchId,
    title: typeof alert.title === "string" ? alert.title : title,
    body: typeof alert.body === "string" ? alert.body : body,
    bookingUrl,
  };
}

export function setPendingAlert(alert: PushAlert | null) {
  pending = alert;
  emit();
}

export function initPushTapListener(): void {
  if (!isNativePush()) return;
  void PushNotifications.addListener("pushNotificationActionPerformed", ({ notification }) => {
    const alert = parsePushAlert(notification.data, notification.title, notification.body);
    if (!alert) return;
    track("push_alert_opened", { watch_id: alert.watchId });
    setPendingAlert(alert);
  });
  // While the app is open the banner shows (capacitor.config); refresh the
  // watchlist so it matches.
  void PushNotifications.addListener("pushNotificationReceived", () => {
    window.dispatchEvent(new Event("campable:watch-alert"));
  });
}

const clearPendingAlert = () => setPendingAlert(null);

export function usePendingAlert(): [PushAlert | null, () => void] {
  const alert = useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => pending,
  );
  return [alert, clearPendingAlert];
}
