import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// Lets us `import` from the shared-design directory (one level above mvp/)
// so the canvas algorithms used by summary.html mocks also drive the MVP.
const sharedDesignDir = path.resolve(__dirname, '..', 'shared-design')

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@shared': sharedDesignDir,
    },
  },
  server: {
    fs: { allow: [sharedDesignDir, path.resolve(__dirname)] },
  },
})
