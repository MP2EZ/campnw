import { describe, test, expect, vi, beforeEach } from "vitest";

const plugin = vi.hoisted(() => ({
  listeners: {} as Record<string, (arg: unknown) => void>,
  receive: "prompt" as string,
  afterRequest: "granted" as string,
  register: vi.fn(),
}));
const prefs = vi.hoisted(() => ({ store: {} as Record<string, string> }));
const api = vi.hoisted(() => ({ registerDeviceToken: vi.fn(), deleteDeviceToken: vi.fn() }));

vi.mock("@capacitor/push-notifications", () => ({
  PushNotifications: {
    checkPermissions: async () => ({ receive: plugin.receive }),
    requestPermissions: async () => {
      plugin.receive = plugin.afterRequest;
      return { receive: plugin.receive };
    },
    register: plugin.register,
    addListener: async (name: string, fn: (arg: unknown) => void) => {
      plugin.listeners[name] = fn;
      return { remove: async () => { delete plugin.listeners[name]; } };
    },
  },
}));
vi.mock("@capacitor/preferences", () => ({
  Preferences: {
    get: async ({ key }: { key: string }) => ({ value: prefs.store[key] ?? null }),
    set: async ({ key, value }: { key: string; value: string }) => { prefs.store[key] = value; },
    remove: async ({ key }: { key: string }) => { delete prefs.store[key]; },
  },
}));
vi.mock("@capacitor/core", () => ({ Capacitor: { isNativePlatform: () => true } }));
vi.mock("../api", () => api);

import { requestNativePush, unregisterNativePush, nativePermission } from "../lib/nativePush";

const TOKEN = "a1".repeat(32);

beforeEach(() => {
  plugin.listeners = {};
  plugin.receive = "prompt";
  plugin.afterRequest = "granted";
  plugin.register.mockReset().mockImplementation(async () => {
    // iOS answers through the listener, after register() resolves.
    setTimeout(() => plugin.listeners.registration?.({ value: TOKEN }), 0);
  });
  prefs.store = {};
  api.registerDeviceToken.mockReset().mockResolvedValue(undefined);
  api.deleteDeviceToken.mockReset().mockResolvedValue(undefined);
});

describe("nativePush", () => {
  test("asks, registers with APNs, and sends the token to the API", async () => {
    expect(await requestNativePush()).toBe("granted");
    expect(api.registerDeviceToken).toHaveBeenCalledWith(TOKEN);
    expect(prefs.store["campable-apns-token"]).toBe(TOKEN);
    expect(plugin.listeners).toEqual({});
  });

  test("a refusal registers nothing", async () => {
    plugin.afterRequest = "denied";
    expect(await requestNativePush()).toBe("denied");
    expect(plugin.register).not.toHaveBeenCalled();
    expect(api.registerDeviceToken).not.toHaveBeenCalled();
  });

  test("already denied: no second prompt", async () => {
    plugin.receive = "denied";
    expect(await nativePermission()).toBe("denied");
    expect(await requestNativePush()).toBe("denied");
    expect(plugin.register).not.toHaveBeenCalled();
  });

  test("an APNs registration error rejects", async () => {
    plugin.register.mockImplementation(async () => {
      setTimeout(() => plugin.listeners.registrationError?.({ error: "no aps-environment" }), 0);
    });
    await expect(requestNativePush()).rejects.toThrow("APNs registration failed");
    expect(api.registerDeviceToken).not.toHaveBeenCalled();
  });

  test("sign-out deletes the stored token from the API", async () => {
    prefs.store["campable-apns-token"] = TOKEN;
    await unregisterNativePush();
    expect(api.deleteDeviceToken).toHaveBeenCalledWith(TOKEN);
    expect(prefs.store).toEqual({});
  });

  test("sign-out without a stored token calls nothing", async () => {
    await unregisterNativePush();
    expect(api.deleteDeviceToken).not.toHaveBeenCalled();
  });
});
