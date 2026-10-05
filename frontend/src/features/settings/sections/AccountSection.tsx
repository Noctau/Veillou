import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useLogout } from '@/features/auth/useAuthMutations'
import { useMe } from '@/features/auth/useMe'

export function AccountSection() {
  const { data: me } = useMe()
  const logout = useLogout()
  const navigate = useNavigate()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Аккаунт</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pt-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Email</dt>
          <dd>{me?.email}</dd>
          <dt className="text-muted-foreground">Часовой пояс</dt>
          <dd>{me?.timezone}</dd>
        </dl>
        <Button
          variant="outline"
          className="self-start"
          disabled={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) })}
        >
          Выйти
        </Button>
      </CardContent>
    </Card>
  )
}
