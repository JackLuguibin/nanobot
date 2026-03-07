import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

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
        target: 'http://localhost:18791',
        changeOrigin: true,
      },
      '/api/ws': {
        target: 'ws://localhost:18791',
        ws: true,
      },
    },
  },
})
