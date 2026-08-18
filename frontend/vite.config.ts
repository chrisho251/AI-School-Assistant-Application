import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Dev proxies /api → FastAPI on :8000 so the browser never hits CORS locally;
// production builds talk to VITE_API_URL directly (see src/lib/api.ts).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // The backend serves routes at the root (/health, /notebooks…), so strip the
    // /api prefix the client uses in dev. Prod talks to VITE_API_URL directly.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
});
