import { Badge } from '@/components/ui/badge'

import { useHealth } from './useHealth'

export function HealthBadge() {
  const { data, isPending, isError } = useHealth()

  if (isPending) return <Badge variant="secondary">Сервер: проверка…</Badge>
  if (isError || data.status !== 'ok') return <Badge variant="destructive">Сервер недоступен</Badge>
  return <Badge variant="outline">Сервер: ок</Badge>
}
