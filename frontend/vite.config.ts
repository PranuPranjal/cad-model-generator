
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // String shorthand for simple proxy rules
      '/api': {
        target: 'http://localhost:5000', // FastAPI server
        changeOrigin: true,
        secure: false,
      },
      '/output.stl': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/output.step': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
})