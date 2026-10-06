import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'

import { Toaster } from '@/components/ui/sonner'
import { persistOptions } from '@/lib/persist'
import { queryClient } from '@/lib/queryClient'
import { router } from '@/router'

import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      <RouterProvider router={router} />
      <Toaster position="top-center" />
    </PersistQueryClientProvider>
  </StrictMode>,
)
