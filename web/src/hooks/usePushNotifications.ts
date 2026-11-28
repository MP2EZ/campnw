import { useState, useEffect, useCallback } from "react";
import { getVapidKey, subscribePush, track, unsubscribePush } from "../api";
import {
  isNativePush,
  nativePermission,
  requestNativePush,
  unregisterNativePush,
} from "../lib/nativePush";

const SUBSCRIBED_KEY = "campable-push-subscribed";

/** Stop this browser receiving the signed-in user's alerts. Call before
 * sign-out, while the auth header still scopes the server-side delete.
 * Best-effort: a failure must not block signing out. */
export async function unregisterPushDevice(): Promise<void> {
  if (isNativePush()) {
    await unregisterNativePush();
    return;
  }
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

/** In the iOS app, permission lives in iOS Settings and can change while the
 * app is in the background, so read it on mount and on every return. */
function useNativePermission(): [NotificationPermission, (p: NotificationPermission) => void] {
  const [permission, setPermission] = useState<NotificationPermission>("default");
  useEffect(() => {
    if (!isNativePush()) return;
    const read = () => {
      if (document.visibilityState !== "visible") return;
      nativePermission().then(setPermission).catch(() => {});
    };
    read();
    document.addEventListener("visibilitychange", read);
    return () => document.removeEventListener("visibilitychange", read);
  }, []);
  return [permission, setPermission];
}

export function usePushNotifications() {
  const native = isNativePush();
  const [webPermission, setWebPermission] = useState<NotificationPermission>(
    typeof Notification !== "undefined" ? Notification.permission : "default"
  );
  const [nativePerm, setNativePerm] = useNativePermission();
  const permission = native ? nativePerm : webPermission;
  const [webSubscribed, setSubscribed] = useState(false);
  // Native: granted means registered (useNativePushSync registers on sign-in).
  const subscribed = native ? nativePerm === "granted" : webSubscribed;

  useEffect(() => {
    if (localStorage.getItem(SUBSCRIBED_KEY) === "true") {
      setSubscribed(true);
    }
  }, []);

  const subscribe = useCallback(async (): Promise<boolean> => {
    if (isNativePush()) {
      const prior = await nativePermission().catch(() => "default" as const);
      try {
        const result = await requestNativePush();
        setNativePerm(result);
        track("push_permission_result", { result, prior_permission: prior, platform: "ios_native" });
        return result === "granted";
      } catch {
        // Registration failed (no network, APNs unreachable). Permission
        // may still be granted; the next sign-in or launch retries.
        setNativePerm(await nativePermission().catch(() => "default" as const));
        return false;
      }
    }
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return false;
    }

    const registration = await navigator.serviceWorker.ready;
    const vapidKey = await getVapidKey();
    if (!vapidKey) return false;

    const priorPermission = Notification.permission;
    const result = await Notification.requestPermission();
    setWebPermission(result);
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
  }, [setNativePerm]);

  return { permission, subscribed, subscribe, native };
}
