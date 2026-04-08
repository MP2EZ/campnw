#!/usr/bin/env node
/**
 * Generate PNG icons and og:image from favicon.svg.
 * Run: node scripts/generate-icons.mjs
 */
import sharp from "sharp";

const sizes = [
  { name: "icon-16x16.png", size: 16 },
  { name: "icon-32x32.png", size: 32 },
  { name: "icon-180x180.png", size: 180 },
  { name: "icon-192x192.png", size: 192 },
  { name: "icon-512x512.png", size: 512 },
  { name: "apple-touch-icon.png", size: 180 },
];

for (const { name, size } of sizes) {
  await sharp("web/public/favicon.svg")
    .resize(size, size)
    .png()
    .toFile(`web/public/${name}`);
  console.log(`✓ ${name} (${size}×${size})`);
}

// og:image — 1200×630
await sharp("web/public/og-default.svg")
  .resize(1200, 630)
  .png()
  .toFile("web/public/og-default.png");
console.log("✓ og-default.png (1200×630)");
