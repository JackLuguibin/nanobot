import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const host = process.env.VITE_API_HOST || 'localhost'
const port = process.env.VITE_API_PORT || '18791'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: `http://${host}:${port}`,
        changeOrigin: true,
      },
      '/ws': {
        target: `ws://${host}:${port}`,
        ws: true,
      },
    },
  },
})
