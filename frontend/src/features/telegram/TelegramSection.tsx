import { CheckCircle2Icon, CopyIcon, SendIcon } from 'lucide-react'
import { useEffect } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useMe } from '@/features/auth/useMe'

import { useCreateLinkCode, useTelegramStatus, useUnlinkTelegram } from './useTelegram'

function formatTime(iso: string, timeZone?: string) {
  return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone }).format(
    new Date(iso),
  )
}

export function TelegramSection() {
  const { data: me } = useMe()
  const createCode = useCreateLinkCode()
  const code = createCode.data
  const status = useTelegramStatus({ waiting: !!code })
  const unlink = useUnlinkTelegram()

  const linked = status.data?.linked
  const { reset } = createCode

  // Привязалась, пока был показан код -> убираем код и радуемся
  useEffect(() => {
    if (linked && code) {
      toast.success('Telegram привязан')
      reset()
    }
  }, [linked, code, reset])

  const command = code ? `/start ${code.code}` : ''
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command)
      toast.success('Скопировано')
    } catch {
      toast.error('Не удалось скопировать — выделите текст вручную')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Telegram</CardTitle>
        <CardDescription>Напоминания и быстрый ввод дел через бота.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pt-4">
        {status.isPending && <Skeleton className="h-9 w-48" />}

        {linked && (
          <div className="flex flex-wrap items-center gap-3">
            <span className="flex items-center gap-2 text-sm">
              <CheckCircle2Icon className="size-4 text-primary" />
              Привязан
            </span>
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              disabled={unlink.isPending}
              onClick={() => unlink.mutate()}
            >
              Отвязать
            </Button>
          </div>
        )}

        {status.data && !linked && !code && (
          <Button
            className="self-start"
            disabled={createCode.isPending}
            onClick={() => createCode.mutate()}
          >
            Привязать Telegram
          </Button>
        )}

        {!linked && code && (
          <div className="flex flex-col gap-3">
            {code.deep_link ? (
              <Button asChild size="lg">
                <a href={code.deep_link} target="_blank" rel="noreferrer">
                  <SendIcon />
                  Открыть бота
                </a>
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">
                Имя бота не настроено на сервере — откройте бота вручную.
              </p>
            )}
            <p className="text-sm text-muted-foreground">
              {code.deep_link ? 'Или отправьте боту команду:' : 'Отправьте боту команду:'}
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-md bg-muted px-3 py-2 font-mono text-sm select-all">
                {command}
              </code>
              <Button variant="outline" size="icon" aria-label="Скопировать" onClick={copy}>
                <CopyIcon />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Код одноразовый, действует до {formatTime(code.expires_at, me?.timezone)}. Ждём
              привязку…
            </p>
            <Button variant="ghost" size="sm" className="self-start" onClick={() => createCode.mutate()}>
              Новый код
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
