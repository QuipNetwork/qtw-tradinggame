import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { rm } from 'node:fs/promises'

// Lets us `import` from the shared-design directory (one level above mvp/)
// so the canvas algorithms used by design-doc.html mocks also drive the MVP.
const sharedDesignDir = path.resolve(__dirname, '..', 'shared-design')

// Keep the design-doc reference imagery out of the production build. The symlink
// `public/reference-files` (~33 MB of internal design photos) is consumed only
// by design-doc.html; Vite would otherwise copy it into dist/ and serve it
// publicly. Dev still resolves the symlink normally.
function stripReferenceFiles(): Plugin {
  return {
    name: 'strip-reference-files',
    apply: 'build',
    closeBundle: async () => {
      await rm(path.resolve(__dirname, 'dist', 'reference-files'), { recursive: true, force: true })
    },
  }
}

export default defineConfig({
  plugins: [react(), stripReferenceFiles()],
  resolve: {
    alias: {
      '@shared': sharedDesignDir,
    },
  },
  server: {
    fs: { allow: [sharedDesignDir, path.resolve(__dirname)] },
  },
  build: {
    // Emit sourcemaps for crash triage without referencing them from the bundle.
    sourcemap: 'hidden',
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
})
