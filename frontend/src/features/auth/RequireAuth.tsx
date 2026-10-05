import { Loader2Icon } from 'lucide-react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/errors'

import { useMe } from './useMe'

export function RequireAuth() {
  const { data: me, isPending, isError, error, refetch } = useMe()
  const location = useLocation()

  if (isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
        <p className="text-muted-foreground">{errorMessage(error)}</p>
        <Button variant="outline" onClick={() => refetch()}>
          Повторить
        </Button>
      </div>
    )
  }
  if (!me) {
    const next = location.pathname + location.search
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }
  return <Outlet />
}
