import React from 'react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import posthog from 'posthog-js'
import { PostHogProvider } from 'posthog-js/react'
import App from './App.tsx'
import { AuthProvider } from './hooks/useAuth'

const phKey = import.meta.env.VITE_PUBLIC_POSTHOG_PROJECT_TOKEN;

if (phKey) {
  posthog.init(phKey, {
    api_host: import.meta.env.VITE_PUBLIC_POSTHOG_HOST || "https://eu.i.posthog.com",
    ui_host: "https://eu.posthog.com",
    person_profiles: "always",
    capture_pageview: true,
    capture_pageleave: true,
    enable_recording_console_log: false,
    session_recording: { maskAllInputs: true },
  });
}

// axe-core accessibility checks in development only
if (import.meta.env.DEV) {
  import('@axe-core/react').then((axe) => {
    import('react-dom').then((ReactDOM) => {
      axe.default(React, ReactDOM, 1000)
    })
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PostHogProvider client={posthog}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </PostHogProvider>
  </StrictMode>,
)

// Register service worker for push notifications
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
