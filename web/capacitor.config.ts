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
  },
};

export default config;
