import { createBrowserRouter } from 'react-router'

import { AppLayout } from '@/components/layout/AppLayout'
import { RequireAuth } from '@/features/auth/RequireAuth'
import { AddPage } from '@/pages/AddPage'
import { InboxPage } from '@/pages/InboxPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { StudyPage } from '@/pages/StudyPage'
import { TodayPage } from '@/pages/TodayPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <TodayPage /> },
          {
            // FullCalendar тяжёлый — отдельным чанком
            path: 'calendar',
            lazy: async () => ({ Component: (await import('@/pages/CalendarPage')).CalendarPage }),
          },
          { path: 'add', element: <AddPage /> },
          { path: 'study', element: <StudyPage /> },
          { path: 'inbox', element: <InboxPage /> },
          { path: 'settings', element: <SettingsPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
])
