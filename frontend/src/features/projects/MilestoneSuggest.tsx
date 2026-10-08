import {
  AlertTriangleIcon,
  ClockIcon,
  Loader2Icon,
  PlusIcon,
  RefreshCwIcon,
  SparklesIcon,
  Trash2Icon,
} from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { jobResult, useJob } from '@/features/ai/useJob'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { todayIn } from '@/lib/time'

import {
  type MilestoneSuggestion,
  type ProjectDetail,
  useApplyMilestones,
  useDismissMilestones,
  useLatestMilestones,
  useSuggestMilestones,
} from './useProjects'

type Row = MilestoneSuggestion & { key: number }

let nextKey = 0
const withKeys = (items: MilestoneSuggestion[]): Row[] => items.map((m) => ({ ...m, key: nextKey++ }))
const strip = (rows: Row[]): MilestoneSuggestion[] =>
  rows
    .filter((r) => r.title.trim())
    .map(({ title, date, note }) => ({
      title: title.trim(),
      date: date || null,
      note,
    }))

/**
 * «Предложить этапы» (M13.2): ИИ по описанию и итоговому сроку предлагает этапы
 * с датами; их можно поправить, удалить, добавить, перегенерировать с
 * комментарием. «Сохранить» добавляет их к уже существующим этапам.
 *
 * Черновик живёт в джобе: можно закрыть окно или страницу — кнопка в разделе
 * «Этапы» вернёт к нему.
 */
export function MilestoneSuggest({ project }: { project: ProjectDetail }) {
  const { data: latest } = useLatestMilestones(project.id)
  const suggest = useSuggestMilestones(project.id)
  const [open, setOpen] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const current = jobId ?? latest?.id ?? null

  const run = (body: { comment?: string | null; previous?: MilestoneSuggestion[] } = {}) =>
    suggest.mutate(
      { comment: body.comment || null, previous: body.previous ?? [] },
      {
        onSuccess: (id) => {
          setJobId(id)
          setOpen(true)
        },
      },
    )

  const ready = latest?.status === 'done'
  return (
    <>
      {latest && !open ? (
        <Button size="sm" variant={ready ? 'default' : 'ghost'} onClick={() => setOpen(true)}>
          {ready ? <SparklesIcon /> : <Loader2Icon className="animate-spin" />}
          {ready ? 'Этапы от ИИ готовы' : 'ИИ думает…'}
        </Button>
      ) : (
        <Button size="sm" variant="ghost" disabled={suggest.isPending} onClick={() => run()}>
          <SparklesIcon /> Предложить
        </Button>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Этапы для «{project.title}»</DialogTitle>
            <DialogDescription>
              ИИ предлагает этапы по описанию и итоговому сроку. Поправьте — и сохраните: они добавятся к текущим.
            </DialogDescription>
          </DialogHeader>
          {current && (
            <Review
              key={current}
              project={project}
              jobId={current}
              regenerating={suggest.isPending}
              onRegenerate={run}
              onClose={() => {
                setOpen(false)
                setJobId(null)
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function Review({
  project,
  jobId,
  regenerating,
  onRegenerate,
  onClose,
}: {
  project: ProjectDetail
  jobId: string
  regenerating: boolean
  onRegenerate: (body: { comment?: string | null; previous?: MilestoneSuggestion[] }) => void
  onClose: () => void
}) {
  const tz = useTimeZone()
  const { data: job } = useJob(jobId)
  const apply = useApplyMilestones(project.id)
  const dismiss = useDismissMilestones(project.id)
  const draft = jobResult(job, 'milestones')
  const [rows, setRows] = useState<Row[] | null>(null)
  const [comment, setComment] = useState('')
  const today = todayIn(tz)

  if (job?.status === 'failed') {
    return (
      <div className="flex flex-col gap-3">
        <p className="flex items-start gap-2 text-sm text-destructive">
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
          {job.error}
        </p>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Закрыть
          </Button>
          <Button disabled={regenerating} onClick={() => onRegenerate({})}>
            <RefreshCwIcon /> Ещё раз
          </Button>
        </DialogFooter>
      </div>
    )
  }
  if (!draft) {
    return (
      <div className="flex items-center gap-3 py-6 text-sm text-muted-foreground" aria-live="polite">
        {job?.waiting ? (
          <ClockIcon className="size-5 shrink-0 text-amber-500" />
        ) : (
          <Loader2Icon className="size-5 shrink-0 animate-spin text-primary" />
        )}
        <div>
          <div className="text-foreground">{job?.waiting ?? 'ИИ продумывает этапы…'}</div>
          <div className="text-xs">Обычно до минуты. Окно можно закрыть — черновик будет ждать в разделе «Этапы».</div>
        </div>
      </div>
    )
  }

  const items = rows ?? withKeys(draft.milestones)
  const update = (key: number, patch: Partial<MilestoneSuggestion>) =>
    setRows(items.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  const valid = strip(items)
  const busy = apply.isPending || dismiss.isPending || regenerating

  return (
    <div className="flex flex-col gap-4">
      {draft.warning && (
        <p className="flex items-start gap-2 text-sm text-amber-600 dark:text-amber-400">
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
          {draft.warning}
        </p>
      )}
      <ul className="flex flex-col gap-3">
        {items.map((r) => (
          <li key={r.key} className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Input aria-label="Этап" value={r.title} onChange={(e) => update(r.key, { title: e.target.value })} />
              <Input
                type="date"
                aria-label="Дата этапа"
                min={today}
                max={project.deadline ?? undefined}
                value={r.date ?? ''}
                onChange={(e) => update(r.key, { date: e.target.value || null })}
                className="w-36 shrink-0"
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Убрать этап"
                className="shrink-0 text-muted-foreground"
                onClick={() => setRows(items.filter((x) => x.key !== r.key))}
              >
                <Trash2Icon />
              </Button>
            </div>
            {r.note && <p className="pl-1 text-xs text-muted-foreground">{r.note}</p>}
          </li>
        ))}
      </ul>
      <Button
        variant="ghost"
        size="sm"
        className="self-start"
        onClick={() => setRows([...items, ...withKeys([{ title: '', date: null, note: '' }])])}
      >
        <PlusIcon /> Этап
      </Button>

      <div className="flex gap-2">
        <Input
          aria-label="Комментарий для ИИ"
          placeholder="Например: «предзащита в мае», «меньше этапов»"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => onRegenerate({ comment: comment.trim(), previous: valid })}
          aria-label="Перегенерировать"
        >
          <RefreshCwIcon />
          <span className="hidden sm:inline">Заново</span>
        </Button>
      </div>

      <DialogFooter>
        <Button variant="ghost" disabled={busy} onClick={() => dismiss.mutate(jobId, { onSuccess: onClose })}>
          Не нужно
        </Button>
        <Button
          disabled={busy || valid.length === 0}
          onClick={() => apply.mutate({ milestones: valid, job_id: jobId }, { onSuccess: onClose })}
        >
          Сохранить {valid.length || ''}
        </Button>
      </DialogFooter>
    </div>
  )
}
