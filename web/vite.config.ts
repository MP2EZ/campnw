import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { visualizer } from 'rollup-plugin-visualizer'

// https://vite.dev/config/
export default defineConfig({
  envDir: '..',
  plugins: [
    react(),
    visualizer({ filename: 'stats.html' }),
  ],
  server: {
    // PostHog snippet uses '/ingest' as api_host. In production both
    // frontend and backend share an origin so the FastAPI /ingest/{path}
    // proxy works directly. In local dev the Vite server (:5173) and
    // FastAPI (:8000) are different ports, so forward /ingest to the
    // backend so the SDK script and event ingest both work.
    proxy: {
      '/ingest': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/leaflet/')) return 'leaflet'
          if (id.includes('react-markdown') || id.includes('remark-parse') || id.includes('remark-rehype')) {
            return 'markdown'
          }
        },
      },
    },
  },
})
