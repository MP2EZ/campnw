import { createClient } from "@supabase/supabase-js";
import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";

const supabaseUrl =
  import.meta.env.VITE_PUBLIC_SUPABASE_URL || "http://localhost:54321";
const supabaseAnonKey =
  import.meta.env.VITE_PUBLIC_SUPABASE_ANON_KEY || "placeholder";

// On native, WKWebView purges localStorage under storage pressure, which
// silently logs users out. Back the Supabase session with @capacitor/preferences
// (native keychain/prefs) instead. Web keeps the default localStorage adapter,
// so passing no options here leaves web behavior byte-identical.
const capacitorStorage = {
  getItem: async (key: string) => (await Preferences.get({ key })).value,
  setItem: async (key: string, value: string) => {
    await Preferences.set({ key, value });
  },
  removeItem: async (key: string) => {
    await Preferences.remove({ key });
  },
};

export const supabase = createClient(
  supabaseUrl,
  supabaseAnonKey,
  Capacitor.isNativePlatform()
    ? {
        auth: {
          storage: capacitorStorage,
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: false,
        },
      }
    : undefined,
);
