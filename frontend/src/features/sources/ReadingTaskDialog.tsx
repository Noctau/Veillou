import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { formatMinutes } from '@/features/tasks/labels'
import { wallToUtc } from '@/lib/time'

import { type Source, useCreateReadingTask } from './useSources'

const ESTIMATES = [30, 60, 120, 240]

type Props = { source: Source | null; onOpenChange: (open: boolean) => void }

/** «Прочитать главы 3–5» из источника: что читать, до когда, сколько займёт. */
export function ReadingTaskDialog({ source, onOpenChange }: Props) {
  return (
    <Dialog open={!!source} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Задание на чтение</DialogTitle>
          <DialogDescription>{source?.title}</DialogDescription>
        </DialogHeader>
        {source && <ReadingForm key={source.id} source={source} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function ReadingForm({ source, onDone }: { source: Source; onDone: () => void }) {
  const tz = useTimeZone()
  const navigate = useNavigate()
  const create = useCreateReadingTask()
  const [chapters, setChapters] = useState('')
  const [deadline, setDeadline] = useState('')
  const [estimate, setEstimate] = useState<number | null>(null)

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate(
          {
            id: source.id,
            body: {
              chapters: chapters.trim(),
              deadline: deadline ? wallToUtc(deadline, '23:59', tz) : null,
              estimate_min: estimate,
            },
          },
          {
            onSuccess: (task) => {
              onDone()
              toast.success('Задание создано', {
                description: task.title,
                action: { label: 'Открыть', onClick: () => navigate(`/tasks/${task.id}`) },
              })
            },
          },
        )
      }}
    >
      <Field>
        <FieldLabel htmlFor="rt-chapters">Что прочитать</FieldLabel>
        <Input
          id="rt-chapters"
          autoFocus
          value={chapters}
          placeholder="главы 3–5 (пусто — весь источник)"
          onChange={(e) => setChapters(e.target.value)}
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="rt-deadline">До какого дня</FieldLabel>
        <Input id="rt-deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>Примерно займёт</FieldLabel>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          className="w-full"
          value={estimate ? String(estimate) : ''}
          onValueChange={(v) => setEstimate(v ? Number(v) : null)}
        >
          {ESTIMATES.map((m) => (
            <ToggleGroupItem key={m} value={String(m)} className="flex-1">
              {formatMinutes(m)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
      <DialogFooter>
        <Button type="submit" disabled={create.isPending}>
          Создать задание
        </Button>
      </DialogFooter>
    </form>
  )
}
