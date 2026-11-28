// Native (APNs) push in the iOS shell. The web build uses the service
// worker path in hooks/usePushNotifications instead.
//
// The device token is a delivery address: it goes to our API and to
// Preferences, never to analytics, logs or error messages.
import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";
import { PushNotifications } from "@capacitor/push-notifications";
import { deleteDeviceToken, registerDeviceToken } from "../api";

export type PushPermission = "granted" | "denied" | "default";

const TOKEN_KEY = "campable-apns-token";
const REGISTRATION_TIMEOUT_MS = 15_000;

export const isNativePush = (): boolean => Capacitor.isNativePlatform();

function toPermission(receive: string): PushPermission {
  if (receive === "granted") return "granted";
  if (receive === "denied") return "denied";
  return "default";
}

export async function nativePermission(): Promise<PushPermission> {
  const { receive } = await PushNotifications.checkPermissions();
  return toPermission(receive);
}

/** Ask APNs for this phone's token. iOS answers through listeners, not the
 * register() promise, so wait for whichever listener fires first. */
async function nextToken(): Promise<string> {
  const handles: { remove: () => Promise<void> }[] = [];
  try {
    return await new Promise<string>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("APNs registration timed out")),
        REGISTRATION_TIMEOUT_MS,
      );
      void PushNotifications.addListener("registration", (t) => {
        clearTimeout(timer);
        resolve(t.value);
      }).then((h) => handles.push(h));
      void PushNotifications.addListener("registrationError", () => {
        clearTimeout(timer);
        reject(new Error("APNs registration failed"));
      }).then((h) => handles.push(h));
      PushNotifications.register().catch((e) => {
        clearTimeout(timer);
        reject(e);
      });
    });
  } finally {
    await Promise.all(handles.map((h) => h.remove()));
  }
}

/** With permission already granted, send this phone's token to the API for
 * the signed-in user. Also moves the phone to whoever signed in last. */
export async function registerNativePush(): Promise<void> {
  const token = await nextToken();
  await registerDeviceToken(token);
  await Preferences.set({ key: TOKEN_KEY, value: token });
}

/** Show the system prompt if iOS hasn't asked yet, then register. iOS shows
 * that prompt once per install, so callers explain first. */
export async function requestNativePush(): Promise<PushPermission> {
  let permission = await nativePermission();
  if (permission === "default") {
    permission = toPermission((await PushNotifications.requestPermissions()).receive);
  }
  if (permission === "granted") await registerNativePush();
  return permission;
}

/** Stop this phone receiving the account's alerts. Best-effort: sign-out
 * must not wait on it failing. */
export async function unregisterNativePush(): Promise<void> {
  try {
    const { value } = await Preferences.get({ key: TOKEN_KEY });
    if (value) {
      await deleteDeviceToken(value).catch(() => {});
      await Preferences.remove({ key: TOKEN_KEY });
    }
  } catch {
    // Preferences unavailable; nothing stored to clear.
  }
}

/** Open this app's page in iOS Settings. Capacitor hands non-web URLs from
 * window.open to UIApplication.open. */
export function openAppSettings(): void {
  window.open("app-settings:", "_blank");
}
