import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
  server: {
    proxy: {
      '/state': 'http://127.0.0.1:5151',
      '/transcript': 'http://127.0.0.1:5151',
      '/restart': 'http://127.0.0.1:5151',
      '/chat': 'http://127.0.0.1:5151',
      '/new-conversation': 'http://127.0.0.1:5151',
      '/conversations': 'http://127.0.0.1:5151',
    },
  },
})
