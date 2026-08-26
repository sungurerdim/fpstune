import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  // Relative asset URLs, so the built UI works wherever it is served from.
  // The default `/` emits `<script src="/assets/...">`, which is correct only
  // at the site root — and the packaged app mounts this bundle under `/ui`, so
  // the browser asked for `/assets/...`, got 404s for the script and the
  // stylesheet, and rendered a blank page with a perfectly healthy 200 for
  // index.html. `./` makes the same build correct at any mount point.
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
