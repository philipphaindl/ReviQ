/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In docker-compose the backend is reachable as "slr-backend"; outside docker
// (e.g. local visual checks, manual `npm run dev`) the developer can point at
// http://localhost:8000 via VITE_API_PROXY.
const proxyTarget = process.env.VITE_API_PROXY ?? 'http://slr-backend:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api':    proxyTarget,
      '/health': proxyTarget,
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/utils/**/*.ts', 'src/components/charts/**/*.tsx'],
    },
  },
})
