import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// Меняется вместе с API -> офлайн-кэш TanStack Query от старой схемы сбрасывается
const apiSchemaHash = createHash('sha256')
  .update(readFileSync(path.resolve(__dirname, 'openapi.json')))
  .digest('hex')
  .slice(0, 12)

export default defineConfig({
  define: { __API_SCHEMA_HASH__: JSON.stringify(apiSchemaHash) },
  plugins: [
    react(),
    tailwindcss(),
    // Свой service worker: офлайн-оболочка, кэш API, «Поделиться», push (src/sw/sw.ts)
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src/sw',
      filename: 'sw.ts',
      injectRegister: 'auto',
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png', 'badge-96.png'],
      manifest: {
        id: '/',
        name: 'Veillou',
        short_name: 'Veillou',
        description: 'Учёба, дела и напоминания',
        lang: 'ru',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        theme_color: '#0a0a0a',
        background_color: '#0a0a0a',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/pwa-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        shortcuts: [
          { name: 'Добавить', short_name: 'Добавить', url: '/add', icons: [{ src: '/pwa-192.png', sizes: '192x192' }] },
          { name: 'Ящик', short_name: 'Ящик', url: '/inbox', icons: [{ src: '/pwa-192.png', sizes: '192x192' }] },
        ],
        // «Поделиться» из любого приложения (Android). POST ловит service worker.
        share_target: {
          action: '/share-target',
          method: 'POST',
          enctype: 'multipart/form-data',
          params: {
            title: 'title',
            text: 'text',
            url: 'url',
            files: [{ name: 'files', accept: ['image/*', 'application/pdf'] }],
          },
        },
      },
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
      // В dev тоже: подписку на push можно проверить без сборки
      devOptions: { enabled: true, type: 'module' },
    }),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: true, // доступ с телефона по LAN
    port: 5173,
    proxy: {
      // API_PROXY — если на 8000 уже занят другой копией бэкенда
      '/api': process.env.API_PROXY ?? 'http://localhost:8000',
    },
  },
})
