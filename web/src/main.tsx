import React from 'react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { AuthProvider } from './hooks/useAuth'

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
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
