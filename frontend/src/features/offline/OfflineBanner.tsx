import { WifiOffIcon } from 'lucide-react'

import { useOnline } from './useOnline'

export function OfflineBanner() {
  const online = useOnline()
  if (online) return null
  return (
    <div
      role="status"
      className="sticky top-0 z-30 -mx-4 -mt-4 mb-4 flex items-center justify-center gap-2 bg-muted px-4 py-1.5 text-xs text-muted-foreground"
    >
      <WifiOffIcon className="size-3.5" />
      Нет сети — показано сохранённое, изменения недоступны
    </div>
  )
}
