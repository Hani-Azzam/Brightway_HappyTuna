import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The Express API runs on :3000. In dev we proxy /api there; the production build is emitted to
// ../public/app and served as static files by Express.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:3000',
    },
  },
  build: {
    outDir: '../public/app',
    emptyOutDir: true,
  },
  base: '/app/',
});
