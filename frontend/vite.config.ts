import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  plugins: [react()],

  // Production assets are collected into Django's STATIC_ROOT and served
  // under /static/, so the built index.html has to reference them there.
  // Dev stays at "/" -- base applies to the dev server too, and "/static/"
  // would move the whole app to http://localhost:5173/static/.
  base: command === 'build' ? '/static/' : '/',

  server: {
    port: 5173,
    // Proxy /api to Django in development. This keeps the frontend
    // same-origin, so there is no CORS preflight and no need for
    // django-cors-headers.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
}))
