import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://slr-backend:8000',
      '/health': 'http://slr-backend:8000',
    },
  },
})
