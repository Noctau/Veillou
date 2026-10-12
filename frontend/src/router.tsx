import type { ComponentType } from 'react'
import { createBrowserRouter } from 'react-router'

import { AppLayout } from '@/components/layout/AppLayout'
import { RequireAuth } from '@/features/auth/RequireAuth'
import { StudyRedirect, SubjectRedirect } from '@/pages/LegacyRedirects'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { TodayPage } from '@/pages/TodayPage'

// «Сегодня» — стартовый экран, грузится сразу; остальные разделы — отдельными чанками
function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  return async () => ({ Component: (await load())[name] })
}

export const router = createBrowserRouter([
  { path: '/login', lazy: page(() => import('@/pages/LoginPage'), 'LoginPage') },
  {
    element: <RequireAuth />,
    children: [
      { path: 'onboarding', lazy: page(() => import('@/pages/OnboardingPage'), 'OnboardingPage') },
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <TodayPage /> },
          { path: 'calendar', lazy: page(() => import('@/pages/CalendarPage'), 'CalendarPage') },
          { path: 'add', lazy: page(() => import('@/pages/AddPage'), 'AddPage') },
          { path: 'areas', lazy: page(() => import('@/pages/AreasPage'), 'AreasPage') },
          { path: 'study', element: <StudyRedirect /> },
          { path: 'tasks/:taskId', lazy: page(() => import('@/pages/TaskPage'), 'TaskPage') },
          {
            path: 'tasks/:taskId/breakdown',
            lazy: page(() => import('@/pages/BreakdownPage'), 'BreakdownPage'),
          },
          { path: 'areas/:areaId', lazy: page(() => import('@/pages/AreaPage'), 'AreaPage') },
          { path: 'subjects/:subjectId', element: <SubjectRedirect /> },
          { path: 'notes/:noteId', lazy: page(() => import('@/pages/NotePage'), 'NotePage') },
          { path: 'projects/:projectId', lazy: page(() => import('@/pages/ProjectPage'), 'ProjectPage') },
          { path: 'inbox', lazy: page(() => import('@/pages/InboxPage'), 'InboxPage') },
          { path: 'review', lazy: page(() => import('@/pages/ReviewPage'), 'ReviewPage') },
          { path: 'review/week', lazy: page(() => import('@/pages/WeeklyReviewPage'), 'WeeklyReviewPage') },
          { path: 'settings', lazy: page(() => import('@/pages/SettingsPage'), 'SettingsPage') },
          { path: 'setup', lazy: page(() => import('@/pages/SetupPage'), 'SetupPage') },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
])
