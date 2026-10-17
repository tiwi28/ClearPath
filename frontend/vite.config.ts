import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: {
    // HTTPS tunnels for phone testing (real GPS needs a secure page).
    allowedHosts: ['.trycloudflare.com', '.ngrok-free.app'],
    // Bind mounts from Windows/macOS hosts do not deliver file events into the container.
    watch: process.env.VITE_USE_POLLING ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
