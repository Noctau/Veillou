import {
  BookOpenIcon,
  CalendarDaysIcon,
  InboxIcon,
  PlusIcon,
  SettingsIcon,
  SunIcon,
  type LucideIcon,
} from 'lucide-react'

export type NavItem = {
  to: string
  label: string
  icon: LucideIcon
  primary?: boolean
}

// Порядок нижней панели: Сегодня · Календарь · ＋ · Учёба · Ящик
export const mainNav: NavItem[] = [
  { to: '/', label: 'Сегодня', icon: SunIcon },
  { to: '/calendar', label: 'Календарь', icon: CalendarDaysIcon },
  { to: '/add', label: 'Добавить', icon: PlusIcon, primary: true },
  { to: '/study', label: 'Учёба', icon: BookOpenIcon },
  { to: '/inbox', label: 'Ящик', icon: InboxIcon },
]

export const settingsNav: NavItem = { to: '/settings', label: 'Настройки', icon: SettingsIcon }
