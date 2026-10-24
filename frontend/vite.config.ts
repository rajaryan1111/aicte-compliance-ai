import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// The browser must never call localhost directly: the dev server proxies /api
// to the FastAPI backend so the app works behind the preview host.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const backend = env.VITE_BACKEND_ORIGIN || 'http://127.0.0.1:8000';

  return {
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/health': { target: backend, changeOrigin: true },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
  },
  };
});
