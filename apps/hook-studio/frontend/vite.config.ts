import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/hook-studio/',
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/hook-studio/api': {
        target: 'http://127.0.0.1:8011',
        rewrite: path => path.replace(/^\/hook-studio/, ''),
      },
    },
  },
})
