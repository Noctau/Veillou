import { Navigate, NavLink, Outlet, useLocation } from 'react-router'

import { OfflineBanner } from '@/features/offline/OfflineBanner'
import { useOfflinePrefetch } from '@/features/offline/useOfflinePrefetch'
import { useOnline } from '@/features/offline/useOnline'
import { PlanSheet } from '@/features/plan/PlanSheet'
import { useSettings } from '@/features/settings/useSettings'
import { cn } from '@/lib/utils'

import { useAreas, useAreaTypes } from '@/features/areas/useAreas'

import { buildNav, fixedNav, MOBILE_SLOTS, settingsNav, type NavItem } from './nav'

/** «Сферы» не горят на странице одного типа или одной сферы, вынесенной во вкладку. */
function useNavItems() {
  const { data: settings } = useSettings()
  const { data: areaTypes } = useAreaTypes()
  const { data: areas } = useAreas()
  const chosen = buildNav(settings?.nav ?? ['areas', 'inbox'], areaTypes, areas)
  return { all: [...fixedNav, ...chosen], mobile: [...fixedNav, ...chosen.slice(0, MOBILE_SLOTS)] }
}

/** Активна ли вкладка: адрес совпадает с учётом `?type=` у вкладки типа сфер. */
function useActive(item: NavItem) {
  const { pathname, search } = useLocation()
  const [path, query] = item.to.split('?')
  if (query) return pathname === path && search === `?${query}`
  if (path === '/') return pathname === '/'
  if (path === '/areas') return pathname.startsWith('/areas') && !search.includes('type=')
  return pathname === path || pathname.startsWith(`${path}/`)
}

function SidebarLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  const active = useActive(item)
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={cn(
        'flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
        active && 'bg-sidebar-accent font-medium text-sidebar-accent-foreground',
      )}
    >
      <Icon className="size-4" />
      {item.label}
    </NavLink>
  )
}

function BottomLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  const active = useActive(item)
  if (item.primary) {
    return (
      <NavLink
        to={item.to}
        aria-label={item.label}
        className="flex flex-1 items-center justify-center"
      >
        <span className="flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg">
          <Icon className="size-6" />
        </span>
      </NavLink>
    )
  }
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={cn(
        'flex min-w-0 flex-1 flex-col items-center justify-center gap-1 text-[11px] text-muted-foreground',
        active && 'text-foreground',
      )}
    >
      <Icon className="size-5" />
      <span className="max-w-full truncate px-1">{item.label}</span>
    </NavLink>
  )
}

export function AppLayout() {
  const online = useOnline()
  useOfflinePrefetch(online)
  const { data: settings } = useSettings()
  const { pathname } = useLocation()
  const nav = useNavItems()

  // Первый вход — короткая настройка. «Поделиться» (/add) не перехватываем.
  if (settings && !settings.onboarding_done && pathname !== '/add') {
    return <Navigate to="/onboarding" replace />
  }

  return (
    <div className="min-h-dvh bg-background text-foreground lg:flex">
      <aside className="hidden w-60 shrink-0 flex-col gap-1 border-r border-sidebar-border bg-sidebar p-3 lg:flex">
        <div className="px-3 py-4 text-lg font-semibold">Veillou</div>
        {nav.all.map((item) => (
          <SidebarLink key={item.to} item={item} />
        ))}
        <div className="mt-auto">
          <SidebarLink item={settingsNav} />
        </div>
      </aside>

      <main className="mx-auto w-full max-w-3xl px-4 pt-4 pb-24 lg:pb-8">
        <OfflineBanner />
        <Outlet />
        <PlanSheet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-40 flex h-16 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        {nav.mobile.map((item) => (
          <BottomLink key={item.to} item={item} />
        ))}
      </nav>
    </div>
  )
}
