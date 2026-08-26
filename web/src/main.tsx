import React from 'react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import App from './App.tsx'
import { AuthProvider } from './hooks/useAuth'
import { BillingProvider } from './hooks/useBilling'
import { Capacitor } from '@capacitor/core'
import { initAnalytics } from './api'

// Register platform/version super properties on the snippet-initialized
// PostHog instance before the first event fires.
initAnalytics()

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
    <HelmetProvider>
      <BrowserRouter>
        <AuthProvider>
          <BillingProvider>
            <App />
          </BillingProvider>
        </AuthProvider>
      </BrowserRouter>
    </HelmetProvider>
  </StrictMode>,
)

// Register service worker for push notifications (web only). SWs are flaky in
// WKWebView and redundant once native push lands; native uses APNs instead.
if (!Capacitor.isNativePlatform() && "serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
