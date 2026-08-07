import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "co.campable.app",
  appName: "Campable",
  // Vite production build output. `npx cap sync` copies this into the native
  // project. No `server.url` — assets are bundled and served from
  // capacitor://localhost so the app works without a network round-trip to load.
  webDir: "dist",
  ios: {
    // Match the app's themed background so the launch-to-content transition
    // doesn't flash white.
    backgroundColor: "#f5f5f0",
    // Inset the WebView's scroll view for the safe area so content clears the
    // status bar / Dynamic Island. Default 'never' renders edge-to-edge under
    // the status bar (and env(safe-area-inset-*) reports 0 in this setup).
    contentInset: "always",
  },
};

export default config;
