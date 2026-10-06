import { onlineManager } from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'

/** Есть ли сеть — то же состояние, по которому TanStack Query ставит запросы на паузу. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    (cb) => onlineManager.subscribe(cb),
    () => onlineManager.isOnline(),
  )
}
