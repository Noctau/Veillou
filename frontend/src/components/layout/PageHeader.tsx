import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { settingsNav } from './nav'

export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  const SettingsIcon = settingsNav.icon
  return (
    <header className="mb-4 flex items-center gap-2">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <div className="ml-auto flex items-center gap-2">
        {actions}
        <Link
          to={settingsNav.to}
          aria-label={settingsNav.label}
          className="rounded-lg p-2 text-muted-foreground hover:bg-accent lg:hidden"
        >
          <SettingsIcon className="size-5" />
        </Link>
      </div>
    </header>
  )
}
