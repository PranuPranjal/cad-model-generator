
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/output.stl': 'http://localhost:8000',
      '/output.step': 'http://localhost:8000',
    },
  },
})