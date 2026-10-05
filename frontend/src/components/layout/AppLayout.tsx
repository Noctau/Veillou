import { NavLink, Outlet } from 'react-router'

import { cn } from '@/lib/utils'

import { mainNav, settingsNav, type NavItem } from './nav'

function SidebarLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
          isActive && 'bg-sidebar-accent font-medium text-sidebar-accent-foreground',
        )
      }
    >
      <Icon className="size-4" />
      {item.label}
    </NavLink>
  )
}

function BottomLink({ item }: { item: NavItem }) {
  const Icon = item.icon
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
      className={({ isActive }) =>
        cn(
          'flex flex-1 flex-col items-center justify-center gap-1 text-[11px] text-muted-foreground',
          isActive && 'text-foreground',
        )
      }
    >
      <Icon className="size-5" />
      {item.label}
    </NavLink>
  )
}

export function AppLayout() {
  return (
    <div className="min-h-dvh bg-background text-foreground lg:flex">
      <aside className="hidden w-60 shrink-0 flex-col gap-1 border-r border-sidebar-border bg-sidebar p-3 lg:flex">
        <div className="px-3 py-4 text-lg font-semibold">Veillou</div>
        {mainNav.map((item) => (
          <SidebarLink key={item.to} item={item} />
        ))}
        <div className="mt-auto">
          <SidebarLink item={settingsNav} />
        </div>
      </aside>

      <main className="mx-auto w-full max-w-3xl px-4 pt-4 pb-24 lg:pb-8">
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-40 flex h-16 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        {mainNav.map((item) => (
          <BottomLink key={item.to} item={item} />
        ))}
      </nav>
    </div>
  )
}
