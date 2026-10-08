import { AlertTriangleIcon, ArrowLeftIcon, ClockIcon, BookmarkIcon, CalendarCheckIcon, Loader2Icon, RefreshCwIcon, SparklesIcon } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { jobResult, useJob } from '@/features/ai/useJob'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { describeDeadline, formatMinutes, TASK_TYPE_LABEL } from '@/features/tasks/labels'
import { type TaskDetail, type TaskType, useTask } from '@/features/tasks/useTasks'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'
import { cn } from '@/lib/utils'

import { type DraftStep, fromSteps, timeWarning, toSteps, totalMinutes, validStep } from './draft'
import { StepList } from './StepList'
import { TemplatesDialog } from './TemplatesDialog'
import { useApplyBreakdown, useRecognizePhoto, useStartBreakdown, useTemplates } from './useBreakdown'

const TASK_TYPES = Object.keys(TASK_TYPE_LABEL) as TaskType[]

type Meta = { taskType: TaskType; categoryId: string | null; free: number | null; coef: number; warning: string | null }

function Thinking({ children, waiting }: { children: ReactNode; waiting?: string | null }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-6 text-sm text-muted-foreground" aria-live="polite">
        {waiting ? (
          <ClockIcon className="size-5 shrink-0 text-amber-500" />
        ) : (
          <Loader2Icon className="size-5 shrink-0 animate-spin text-primary" />
        )}
        <div>
          <div className="text-foreground">{waiting ?? children}</div>
          <div className="text-xs">
            {waiting
              ? 'Можно закрыть страницу — когда ИИ появится, черновик будет ждать на странице задания.'
              : 'Обычно 10–60 секунд. Можно уйти — черновик появится на странице задания.'}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function Warning({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-sm text-amber-600 dark:text-amber-400">
      <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </p>
  )
}

/** Шаги задания, которые ещё не сделаны, — для «вручную» и предупреждения о замене. */
function openSteps(task: TaskDetail) {
  return task.subtasks.filter((s) => s.status !== 'done')
}

/**
 * Экран проверки разбивки (M10.3): ИИ предлагает шаги, их можно править, удалять,
 * добавлять, переставлять, связывать; «Перегенерировать с комментарием»;
 * «Запланировать» — шаги сохраняются, превью плана открывается в шторке.
 *
 * Адрес держит id джоб (`?job=`, `?photoJob=`), поэтому перезагрузка и ссылка
 * из бота открывают тот же черновик. `?photo=1` — сначала распознать фото задания.
 */
export function BreakdownReview({ taskId }: { taskId: string }) {
  const navigate = useNavigate()
  const tz = useTimeZone()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const jobId = params.get('job')
  const photoJobId = params.get('photoJob')
  const wantPhoto = params.get('photo') === '1'
  // «Шаги из шаблона» — без ИИ: сразу список шаблонов
  const fromTemplate = params.get('templates') === '1' || params.has('template')
  const templateId = params.get('template')

  const { data: task, isError, error } = useTask(taskId)
  const start = useStartBreakdown(taskId)
  const recognize = useRecognizePhoto(taskId)
  const apply = useApplyBreakdown(taskId)
  const { data: job } = useJob(jobId)
  const { data: photoJob } = useJob(photoJobId)
  const { data: templateList } = useTemplates()

  const [draft, setDraft] = useState<DraftStep[] | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [loadedJob, setLoadedJob] = useState<string | null>(null)
  const [comment, setComment] = useState('')
  const [templates, setTemplates] = useState(fromTemplate)

  const setJob = (key: 'job' | 'photoJob', id: string) =>
    setParams(
      (old) => {
        const next = new URLSearchParams(old)
        next.delete('photo')
        next.delete('photoJob')
        next.set(key, id)
        return next
      },
      { replace: true },
    )

  const runBreakdown = (body: { comment?: string } = {}) =>
    start.mutate(
      { comment: body.comment || null, previous: draft ? toSteps(draft) : [] },
      { onSuccess: (id) => setJob('job', id) },
    )

  // Первый заход: сразу фото или разбивка (один раз, даже в StrictMode)
  const started = useRef(false)
  useEffect(() => {
    if (started.current || jobId || photoJobId || fromTemplate) return
    started.current = true
    if (wantPhoto) recognize.mutate(undefined, { onSuccess: (id) => setJob('photoJob', id) })
    else start.mutate({ comment: null, previous: [] }, { onSuccess: (id) => setJob('job', id) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Фото распознано → обновить задание и разбивать
  const photo = jobResult(photoJob, 'photo')
  const chained = useRef<string | null>(null)
  useEffect(() => {
    if (!photo || !photoJobId || chained.current === photoJobId) return
    chained.current = photoJobId
    queryClient.invalidateQueries({ queryKey: queryKeys.task(taskId) })
    if (photo.updated.length) toast.success('Фото распознано — текст добавлен в описание')
    start.mutate({ comment: null, previous: [] }, { onSuccess: (id) => setJob('job', id) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photo, photoJobId])

  // Пришёл черновик — на редактирование (состояние из данных запроса, один раз на джобу)
  const result = jobResult(job, 'breakdown')
  if (result && jobId && loadedJob !== jobId) {
    setLoadedJob(jobId)
    setDraft(fromSteps(result.steps))
    setMeta({
      taskType: result.task_type,
      categoryId: result.category_id,
      free: result.free_minutes,
      coef: result.coef,
      warning: result.warning,
    })
  }

  // «Применить шаблон» со страницы задания
  const template = templateId ? templateList?.find((t) => t.id === templateId) : undefined
  if (template && loadedJob !== `template:${template.id}`) {
    setLoadedJob(`template:${template.id}`)
    setDraft(fromSteps(template.steps))
    setMeta({
      taskType: template.task_type ?? task?.task_type ?? 'other',
      categoryId: null,
      free: null,
      coef: 1,
      warning: null,
    })
  }

  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>
  if (!task) return <Skeleton className="h-60" />

  const manual = (steps: DraftStep[]) => {
    setDraft(steps)
    setMeta((m) => m ?? { taskType: task.task_type, categoryId: null, free: null, coef: 1, warning: null })
  }
  const thinking = start.isPending || (!!jobId && !!job && !result && job.status !== 'failed')
  const photoThinking = recognize.isPending || (!!photoJobId && photoJob?.status !== 'done' && photoJob?.status !== 'failed')
  const failed = job?.status === 'failed' ? job.error : photoJob?.status === 'failed' ? photoJob.error : null
  // ИИ недоступен: пока ждём, можно разбить из шаблона или вручную
  const waiting = job?.waiting ?? photoJob?.waiting ?? null

  const total = draft ? totalMinutes(draft) : 0
  const warn = meta ? timeWarning(total, meta.free, meta.coef) : null
  const canPlan = !!draft && draft.length > 0 && draft.every(validStep) && !apply.isPending
  const replacing = openSteps(task).length
  const due = task.deadline ? describeDeadline(task.deadline, tz) : null

  const plan = () =>
    draft &&
    apply.mutate(
      {
        steps: toSteps(draft),
        task_type: meta?.taskType ?? null,
        category_id: task.category_id ? null : (meta?.categoryId ?? null),
        plan: true,
        // Черновик ИИ применён — задание перестанет о нём напоминать
        job_id: loadedJob && !loadedJob.startsWith('template:') ? loadedJob : null,
      },
      {
        onSuccess: () => {
          toast.success('Шаги сохранены — проверьте план')
          navigate(`/tasks/${taskId}`, { replace: true })
        },
      },
    )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-1">
        <Button variant="ghost" size="icon" aria-label="Назад" className="-ml-2 shrink-0" onClick={() => navigate(-1)}>
          <ArrowLeftIcon />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">Шаги задания</h1>
          <div className="flex flex-wrap gap-x-3 text-sm text-muted-foreground">
            <span className="truncate">{task.title}</span>
            {due && <span className={cn(due.tone === 'overdue' && 'text-destructive')}>{due.text}</span>}
            {meta?.free != null && <span>свободно ~{formatMinutes(meta.free)}</span>}
          </div>
        </div>
      </div>

      {photoThinking && <Thinking waiting={photoJob?.waiting}>Читаю фото задания…</Thinking>}
      {!photoThinking && thinking && !draft && <Thinking waiting={job?.waiting}>ИИ разбивает задание на шаги…</Thinking>}

      {((failed && !thinking) || (fromTemplate && !draft && !thinking) || (!!waiting && !draft)) && (
        <Card>
          <CardContent className="flex flex-col gap-3 py-4">
            {failed && <Warning>{failed}</Warning>}
            <div className="flex flex-wrap gap-2">
              {!waiting && (
                <Button size="sm" onClick={() => runBreakdown()}>
                  {failed ? <RefreshCwIcon /> : <SparklesIcon />} {failed ? 'Ещё раз' : 'Разбить с ИИ'}
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => setTemplates(true)}>
                <BookmarkIcon /> Из шаблона
              </Button>
              {!draft && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    manual(
                      openSteps(task).length
                        ? fromSteps(openSteps(task).map((s) => ({ ...s, depends_on: [] })))
                        : fromSteps([{ title: '', estimate_min: 30, depends_on: [], note: '' }]),
                    )
                  }
                >
                  Вручную
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {draft && (
        <>
          <div className={cn('flex flex-col gap-3', thinking && 'pointer-events-none opacity-50')}>
            {thinking && <Thinking>Перегенерирую…</Thinking>}
            <StepList steps={draft} onChange={setDraft} />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span>
                Итого <span className="font-medium">~{formatMinutes(total)}</span>
                {meta && meta.coef !== 1 && (
                  <span className="text-muted-foreground"> (с вашим темпом ~{formatMinutes(Math.round(total * meta.coef))})</span>
                )}
              </span>
              {meta && (
                <Select value={meta.taskType} onValueChange={(v) => setMeta({ ...meta, taskType: v as TaskType })}>
                  <SelectTrigger size="sm" aria-label="Тип задания">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TASK_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {TASK_TYPE_LABEL[t]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            {warn && <Warning>{warn}</Warning>}
            {meta?.warning && <Warning>ИИ: {meta.warning}</Warning>}
            {replacing > 0 && (
              <p className="text-xs text-muted-foreground">
                Несделанные шаги задания ({replacing}) заменятся этими; сделанные останутся.
              </p>
            )}
          </div>

          <Card>
            <CardContent className="flex flex-col gap-2 py-3">
              <form
                className="flex items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  runBreakdown({ comment: comment.trim() })
                  setComment('')
                }}
              >
                <Input
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="«слишком мелко», «добавь поиск литературы»"
                  aria-label="Комментарий для ИИ"
                />
                <Button type="submit" variant="outline" disabled={thinking}>
                  <SparklesIcon /> <span className="hidden sm:inline">Перегенерировать</span>
                </Button>
              </form>
            </CardContent>
          </Card>
        </>
      )}

      {draft && (
        <div className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-20 lg:bottom-4">
          <div className="flex items-center gap-2 rounded-xl border bg-popover p-2 shadow-lg">
            <Button variant="outline" onClick={() => setTemplates(true)}>
              <BookmarkIcon /> Шаблоны
            </Button>
            <Button className="ml-auto" disabled={!canPlan} onClick={plan}>
              {apply.isPending ? <Loader2Icon className="animate-spin" /> : <CalendarCheckIcon />}
              Запланировать
            </Button>
          </div>
        </div>
      )}

      <TemplatesDialog
        open={templates}
        onOpenChange={setTemplates}
        steps={draft?.every(validStep) ? toSteps(draft) : []}
        taskType={meta?.taskType ?? task.task_type}
        defaultName={TASK_TYPE_LABEL[meta?.taskType ?? task.task_type]}
        onApply={(t) => {
          manual(fromSteps(t.steps))
          if (t.task_type) setMeta((m) => (m ? { ...m, taskType: t.task_type! } : m))
        }}
      />
    </div>
  )
}
