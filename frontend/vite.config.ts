import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Свой service worker (push + кнопки уведомлений). Иконки, кэш API и офлайн — M7.1.
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src/sw',
      filename: 'sw.ts',
      injectRegister: 'auto',
      registerType: 'autoUpdate',
      manifest: {
        name: 'Veillou',
        short_name: 'Veillou',
        lang: 'ru',
        start_url: '/',
        display: 'standalone',
        theme_color: '#0a0a0a',
        background_color: '#0a0a0a',
        icons: [{ src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
      },
      injectManifest: { globPatterns: ['**/*.{js,css,html,svg,woff2}'] },
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
