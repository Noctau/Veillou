import { createBrowserRouter } from 'react-router'

import { AppLayout } from '@/components/layout/AppLayout'
import { AddPage } from '@/pages/AddPage'
import { CalendarPage } from '@/pages/CalendarPage'
import { InboxPage } from '@/pages/InboxPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { StudyPage } from '@/pages/StudyPage'
import { TodayPage } from '@/pages/TodayPage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <TodayPage /> },
      { path: 'calendar', element: <CalendarPage /> },
      { path: 'add', element: <AddPage /> },
      { path: 'study', element: <StudyPage /> },
      { path: 'inbox', element: <InboxPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
