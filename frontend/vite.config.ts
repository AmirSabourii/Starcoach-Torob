import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' so dist/ also works from any static server sub-path
export default defineConfig({
  base: '/app/',
  plugins: [react()],
  build: { assetsInlineLimit: 0 },
})
