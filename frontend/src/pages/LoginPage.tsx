import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoginForm } from '@/features/auth/LoginForm'
import { useMe } from '@/features/auth/useMe'
import { safeNext } from '@/lib/url'

export function LoginPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { data: me } = useMe()
  const next = safeNext(params.get('next'))

  if (me) return <Navigate to={next} replace />

  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-2xl">Veillou</CardTitle>
        </CardHeader>
        <CardContent>
          <LoginForm onSuccess={() => navigate(next, { replace: true })} />
        </CardContent>
      </Card>
    </div>
  )
}
