import {
  CalendarDaysIcon,
  FolderKanbanIcon,
  InboxIcon,
  LayersIcon,
  ListTodoIcon,
  NotebookPenIcon,
  PlusIcon,
  SettingsIcon,
  SunIcon,
  type LucideIcon,
} from 'lucide-react'

import { CATEGORY_ICONS } from '@/features/catalog/icons'
import type { CategoryIconName } from '@/features/catalog/useCatalog'
import { NAV_UI as T } from '@/lib/terms'

export type NavItem = {
  to: string
  label: string
  icon: LucideIcon
  primary?: boolean
  /** Ключ из `settings.nav` (у закреплённых — нет). */
  key?: string
}

// Закреплены всегда: Сегодня · Календарь · ＋
export const fixedNav: NavItem[] = [
  { to: '/', label: T.today, icon: SunIcon },
  { to: '/calendar', label: T.calendar, icon: CalendarDaysIcon },
  { to: '/add', label: T.add, icon: PlusIcon, primary: true },
]

export const settingsNav: NavItem = { to: '/settings', label: T.settings, icon: SettingsIcon }

// Разделы, которые можно вынести во вкладку
export const SECTION_NAV: Record<string, Omit<NavItem, 'key'>> = {
  areas: { to: '/areas', label: T.areas, icon: LayersIcon },
  tasks: { to: '/tasks', label: T.tasks, icon: ListTodoIcon },
  projects: { to: '/projects', label: T.projects, icon: FolderKanbanIcon },
  notes: { to: '/notes', label: T.notes, icon: NotebookPenIcon },
  inbox: { to: '/inbox', label: T.inbox, icon: InboxIcon },
}

// Сколько выбранных вкладок помещается в нижнюю панель телефона (рядом с закреплёнными)
export const MOBILE_SLOTS = 2

type AreaTypeRef = { id: string; name_plural: string; icon: CategoryIconName }
type AreaRef = { id: string; name: string; short_name: string | null; area_type_id: string }

function icon(name: CategoryIconName | undefined): LucideIcon {
  return (name && CATEGORY_ICONS[name]) || LayersIcon
}

/** Вкладки из `settings.nav`: раздел, тип сфер («Ученики») или конкретная сфера.
 *  Ссылки на удалённые сферы и типы пропускаются. */
export function buildNav(keys: string[], areaTypes: AreaTypeRef[] = [], areas: AreaRef[] = []): NavItem[] {
  const types = new Map(areaTypes.map((t) => [t.id, t]))
  const byId = new Map(areas.map((a) => [a.id, a]))
  return keys.flatMap((key): NavItem[] => {
    if (SECTION_NAV[key]) return [{ ...SECTION_NAV[key], key }]
    const [kind, id] = key.split(':')
    if (kind === 'area_type' && types.has(id)) {
      const t = types.get(id)!
      return [{ to: `/areas?type=${id}`, label: t.name_plural, icon: icon(t.icon), key }]
    }
    if (kind === 'area' && byId.has(id)) {
      const a = byId.get(id)!
      return [{ to: `/areas/${id}`, label: a.short_name || a.name, icon: icon(types.get(a.area_type_id)?.icon), key }]
    }
    return []
  })
}
