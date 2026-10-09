import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Отдельно от vite.config.ts: тестам не нужны PWA-плагин и сборка service worker
export default defineConfig({
  plugins: [react()],
  define: { __API_SCHEMA_HASH__: JSON.stringify('test') },
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      include: ['src/lib/**', 'src/features/**/*.ts'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/api/**'],
    },
  },
})
