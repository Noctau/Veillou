import { PlayIcon, StarIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { formatMinutes } from '@/features/tasks/labels'
import { errorMessage } from '@/lib/errors'
import { wallTime } from '@/lib/time'

import { useFree, useStartFree } from './useReview'

const CHOICES = [15, 30, 45, 60, 90, 120]

/** «У меня есть N минут»: лучшее подходящее дело и пара альтернатив; «Начать» — блок на сейчас. */
export function FreeDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const tz = useTimeZone()
  const [minutes, setMinutes] = useState<number | null>(null)
  const { data, isFetching, isError, error } = useFree(open ? minutes : null)
  const start = useStartFree()

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v)
        if (!v) setMinutes(null)
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Сколько есть времени?</DialogTitle>
          <DialogDescription>Подберу шаг задания или дело из ящика, которое влезает и уместно сейчас.</DialogDescription>
        </DialogHeader>
        <ToggleGroup
          type="single"
          variant="outline"
          className="flex-wrap"
          value={minutes ? String(minutes) : ''}
          onValueChange={(v) => v && setMinutes(Number(v))}
        >
          {CHOICES.map((m) => (
            <ToggleGroupItem key={m} value={String(m)} className="px-3">
              {formatMinutes(m)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        {minutes != null && (
          <div className="flex flex-col gap-2">
            {isFetching && !data && <Skeleton className="h-24" />}
            {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
            {data && data.length === 0 && (
              <p className="py-4 text-center text-sm text-muted-foreground">
                Ничего не влезает или сейчас не время для этих дел.
              </p>
            )}
            {data && data.length > 0 && (
              <ul className="flex flex-col gap-1">
                {data.map((item, i) => (
                  <li key={`${item.kind}-${item.id}`} className="flex items-center gap-2 rounded-lg px-2 py-2 hover:bg-muted">
                    {i === 0 ? (
                      <StarIcon className="size-4 shrink-0 text-amber-500" aria-label="Лучшее" />
                    ) : (
                      <span className="size-4 shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{item.title}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {[formatMinutes(item.minutes), item.subtitle].filter(Boolean).join(' · ')}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant={i === 0 ? 'default' : 'outline'}
                      disabled={start.isPending}
                      onClick={() =>
                        start.mutate(item, {
                          onSuccess: (event) => {
                            toast.success(`«${item.title}» — до ${wallTime(event.end, tz)}`)
                            onOpenChange(false)
                            setMinutes(null)
                          },
                        })
                      }
                    >
                      <PlayIcon /> Начать
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
