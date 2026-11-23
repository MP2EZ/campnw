import { useState, useEffect, useCallback } from "react";
import { getVapidKey, subscribePush, track, unsubscribePush } from "../api";

const SUBSCRIBED_KEY = "campable-push-subscribed";

/** Stop this browser receiving the signed-in user's alerts. Call before
 * sign-out, while the auth header still scopes the server-side delete.
 * Best-effort: a failure must not block signing out. */
export async function unregisterPushDevice(): Promise<void> {
  try {
    // getRegistration, not .ready: .ready never settles without a worker.
    const reg = await navigator.serviceWorker?.getRegistration();
    const sub = await reg?.pushManager?.getSubscription();
    if (sub) {
      await unsubscribePush(sub.endpoint).catch(() => {});
      await sub.unsubscribe().catch(() => false);
    }
  } catch {
    // No service worker or push support here.
  }
  localStorage.removeItem(SUBSCRIBED_KEY);
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

export function usePushNotifications() {
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof Notification !== "undefined" ? Notification.permission : "default"
  );
  const [subscribed, setSubscribed] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(SUBSCRIBED_KEY) === "true") {
      setSubscribed(true);
    }
  }, []);

  const subscribe = useCallback(async (): Promise<boolean> => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return false;
    }

    const registration = await navigator.serviceWorker.ready;
    const vapidKey = await getVapidKey();
    if (!vapidKey) return false;

    const priorPermission = Notification.permission;
    const result = await Notification.requestPermission();
    setPermission(result);
    // Push permission is the single gate on whether a watch can ever deliver
    // value. The result was discarded, so "watches created" overstated the
    // reachable alert audience by an unknown factor.
    track("push_permission_result", {
      result,
      // Read from the browser rather than the React state the callback closes
      // over: subscribe() is intentionally dep-free so its identity stays
      // stable, and the state can lag the real permission.
      prior_permission: priorPermission,
    });
    if (result !== "granted") return false;

    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidKey) as BufferSource,
    });

    const key = subscription.getKey("p256dh");
    const auth = subscription.getKey("auth");
    if (!key || !auth) return false;

    const p256dh = btoa(
      String.fromCharCode(...new Uint8Array(key as ArrayBuffer)),
    );
    const authStr = btoa(
      String.fromCharCode(...new Uint8Array(auth as ArrayBuffer)),
    );

    await subscribePush(subscription.endpoint, p256dh, authStr);
    setSubscribed(true);
    localStorage.setItem(SUBSCRIBED_KEY, "true");
    return true;
  }, []);

  return { permission, subscribed, subscribe };
}
