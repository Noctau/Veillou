import {
  BookOpenIcon,
  BriefcaseIcon,
  CalendarIcon,
  CheckIcon,
  ClockIcon,
  InboxIcon,
  Loader2Icon,
  ListTodoIcon,
  NotebookPenIcon,
  SendIcon,
  SparklesIcon,
  XIcon,
} from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { type AttachmentOwner, uploadAttachment } from '@/features/attachments/useAttachments'
import { useCreateBacklog } from '@/features/backlog/useBacklog'
import { useCreateEvent } from '@/features/calendar/useCalendar'
import { useCreateNote } from '@/features/notes/useNotes'
import { type ActionTypeKey, useActionTypes } from '@/features/catalog/useCatalog'
import { WorkTaskDialog } from '@/features/projects/WorkTaskDialog'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { useSubjects } from '@/features/subjects/useSubjects'
import { TASK_TYPE_LABEL } from '@/features/tasks/labels'
import { useCreateTask } from '@/features/tasks/useTasks'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { compressImage } from '@/lib/image'
import { SHARE_PARAM } from '@/lib/pwa-shared'
import { queryKeys } from '@/lib/queryKeys'
import { formatDay, wallDate, wallToUtc } from '@/lib/time'
import { cn } from '@/lib/utils'

import { type AiCardResult, AiParseCard } from './AiParseCard'
import { SharedFiles } from './SharedFiles'
import { type QuickParse, useAiParse, useParseNow, useQuickParse } from './useQuickParse'
import { useShare } from './useShare'

type Kind = 'task' | 'backlog' | 'event' | 'note'

const KINDS: { value: Kind; label: string; icon: typeof InboxIcon }[] = [
  { value: 'task', label: 'Задание', icon: ListTodoIcon },
  { value: 'backlog', label: 'В ящик', icon: InboxIcon },
  { value: 'event', label: 'Событие', icon: CalendarIcon },
  { value: 'note', label: 'Конспект', icon: NotebookPenIcon },
]

const DEFAULT_EVENT_MIN = 60
/** С файлами (из «Поделиться») можно создать только задание или конспект. */
const FILE_KINDS: Kind[] = ['task', 'note']
/** Название задания из фото без подписи — распознавание заменит его (как на сервере). */
const PHOTO_TITLE = 'Задание с фото'

/** Неуверенный ввод ушёл в ИИ: быстрый разбор держим на случай «создать как есть». */
type AiPending = { jobId: string; raw: string; p: QuickParse; day: string | null; subjectId: string | null }

type Saved = { id: string; kind: Kind; title: string; link?: string }

/** Конец события: «с … до …», «на 2 часа» или час по умолчанию. */
function eventEnd(p: QuickParse, start: string, tz: string): string {
  if (p.end_time && p.date) {
    const end = wallToUtc(p.date, p.end_time, tz)
    // «с 23 до 1» — до следующего дня
    return end > start ? end : new Date(new Date(end).getTime() + 86_400_000).toISOString()
  }
  const minutes = p.duration_min ?? DEFAULT_EVENT_MIN
  return new Date(new Date(start).getTime() + minutes * 60_000).toISOString()
}

function Chip({ icon, children, onRemove }: { icon?: ReactNode; children: ReactNode; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border bg-muted/50 py-1 pr-1 pl-2.5 text-xs">
      {icon}
      {children}
      {onRemove ? (
        <button type="button" onClick={onRemove} aria-label="Убрать" className="rounded-full p-0.5 hover:bg-muted">
          <XIcon className="size-3" />
        </button>
      ) : (
        <span className="w-1" />
      )}
    </span>
  )
}

export function QuickAdd() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const tz = useTimeZone()
  const [text, setText] = useState(params.get('text') ?? '')
  const [kindOverride, setKindOverride] = useState<Kind | null>(null)
  const [dropSubject, setDropSubject] = useState(false)
  const [dropDate, setDropDate] = useState(false)
  const [saved, setSaved] = useState<Saved[]>([])
  const [workTask, setWorkTask] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [skipAi, setSkipAi] = useState(false)
  const [ai, setAi] = useState<AiPending | null>(null)
  const aiParse = useAiParse()
  const share = useShare(params.get(SHARE_PARAM), setText)
  const hasFiles = share.files.length > 0
  const onlyImages = hasFiles && share.files.every((f) => f.type.startsWith('image/'))
  const queryClient = useQueryClient()

  const { data: parsed } = useQuickParse(text)
  const parseNow = useParseNow()
  const { data: subjects } = useSubjects()
  const { data: actionTypes } = useActionTypes()
  const createTask = useCreateTask()
  const createBacklog = useCreateBacklog()
  const createEvent = useCreateEvent()
  const createNote = useCreateNote()

  const live = text.trim() ? parsed : undefined
  const wanted: Kind = kindOverride ?? live?.kind_hint ?? (hasFiles ? 'task' : 'backlog')
  const kind: Kind = hasFiles && !FILE_KINDS.includes(wanted) ? 'task' : wanted
  const subject = !dropSubject && live?.subject_id ? subjects?.find((s) => s.id === live.subject_id) : undefined
  const date = dropDate ? null : (live?.date ?? null)
  const needsTime = kind === 'event' && (!date || !live?.time)

  const actionTypeId = (key: ActionTypeKey | null) =>
    (key && actionTypes?.find((a) => a.key === key)?.id) || null

  const reset = () => {
    setText('')
    setKindOverride(null)
    setDropSubject(false)
    setDropDate(false)
    setSkipAi(false)
  }

  const remember = (item: Saved) => setSaved((old) => [item, ...old].slice(0, 5))

  /** Задание или конспект с файлами из «Поделиться»: создаём, грузим файлы, открываем. */
  const saveWithFiles = async () => {
    const raw = text.trim()
    const allImages = share.files.every((f) => f.type.startsWith('image/'))
    if (kind === 'task' && !raw && !allImages) {
      toast.error('Напишите, что за задание')
      return
    }
    setUploading(true)
    let owner: { type: AttachmentOwner; id: string; link: string }
    try {
      const p = raw ? await parseNow(raw) : null
      const day = dropDate ? null : (p?.date ?? null)
      const subjectId = dropSubject ? null : (p?.subject_id ?? null)
      if (kind === 'task') {
        const t = await createTask.mutateAsync({
          title: p?.title || raw || PHOTO_TITLE,
          task_type: p?.task_type ?? 'other',
          description: '',
          subject_id: subjectId,
          action_type_id: actionTypeId(p?.action_type ?? null),
          deadline: day ? (p?.deadline ?? null) : null,
          priority: 'normal',
          subtasks: [],
        })
        // Фото задания — сразу распознать и разбить на шаги
        owner = { type: 'task', id: t.id, link: allImages ? `/tasks/${t.id}/breakdown?photo=1` : `/tasks/${t.id}` }
      } else {
        const n = await createNote.mutateAsync({
          title: p?.title || raw || null,
          kind: allImages ? 'photo' : 'file',
          subject_id: subjectId,
          class_date: day,
          body_md: '',
        })
        owner = { type: 'note', id: n.id, link: `/notes/${n.id}` }
      }
    } catch {
      // Ошибку создания уже показал хук мутации
      setUploading(false)
      return
    }
    try {
      for (const file of share.files) await uploadAttachment(owner.type, owner.id, await compressImage(file))
      share.finish()
      reset()
      navigate(owner.link, { replace: true })
    } catch (error) {
      toast.error(errorMessage(error, 'Не удалось загрузить файл'), {
        description: 'Само задание или конспект создан — добавьте файлы на его странице',
        action: { label: 'Открыть', onClick: () => navigate(owner.link) },
      })
    } finally {
      queryClient.invalidateQueries({ queryKey: queryKeys.attachments(owner.type, owner.id) })
      if (owner.type === 'note') queryClient.invalidateQueries({ queryKey: queryKeys.notesAll })
      setUploading(false)
    }
  }

  const save = async () => {
    if (hasFiles) return saveWithFiles()
    const raw = text.trim()
    if (!raw) return
    let p: QuickParse
    try {
      p = await parseNow(raw)
    } catch (error) {
      toast.error(errorMessage(error))
      return
    }
    const day = dropDate ? null : p.date
    const subjectId = dropSubject ? null : p.subject_id
    const title = p.title || raw
    const restore = () => setText(raw)

    if (kind === 'event') {
      if (!day || !p.time) {
        toast.error('Для события нужно время: «завтра в 14», «в пт с 10 до 12»')
        return
      }
      const start = wallToUtc(day, p.time, tz)
      reset()
      createEvent.mutate(
        { kind: 'personal', title, start, end: eventEnd(p, start, tz), note: '', subject_id: subjectId },
        { onSuccess: (e) => remember({ id: e.id, kind, title, link: '/calendar' }), onError: restore },
      )
      return
    }

    if (kind === 'note') {
      reset()
      createNote.mutate(
        { title, kind: 'text', subject_id: subjectId, class_date: day, body_md: '' },
        { onSuccess: (n) => navigate(`/notes/${n.id}`), onError: restore },
      )
      return
    }

    if (kind === 'backlog') {
      reset()
      createBacklog.mutate(
        { title, note: '', desired_by: day, action_type_id: actionTypeId(p.action_type) },
        { onError: restore },
      )
      remember({ id: crypto.randomUUID(), kind, title, link: '/inbox' })
      return
    }

    if (p.needs_ai && !skipAi) {
      reset()
      aiParse.mutate(raw, {
        onSuccess: (jobId) => setAi({ jobId, raw, p, day, subjectId }),
        onError: restore,
      })
      return
    }

    reset()
    createPlainTask(raw, p, day, subjectId)
  }

  /** Задание по быстрому разбору (без ИИ). */
  const createPlainTask = (raw: string, p: QuickParse, day: string | null, subjectId: string | null) => {
    const title = p.title || raw
    createTask.mutate(
      {
        title,
        task_type: p.task_type ?? 'other',
        description: '',
        subject_id: subjectId,
        action_type_id: actionTypeId(p.action_type),
        deadline: day ? (p.deadline ?? null) : null,
        priority: 'normal',
        subtasks: [],
      },
      {
        onSuccess: (t) => {
          remember({ id: t.id, kind: 'task', title, link: `/tasks/${t.id}` })
          toast.success('Задание добавлено', {
            action: { label: 'Открыть', onClick: () => navigate(`/tasks/${t.id}`) },
          })
        },
        onError: () => setText(raw),
      },
    )
  }

  /** Карточка ИИ подтверждена. */
  const createFromAi = async (card: AiCardResult, breakDown: boolean) => {
    if (card.kind === 'backlog') {
      setAi(null)
      createBacklog.mutate({
        title: card.title,
        note: card.description.slice(0, 2000),
        desired_by: card.deadline ? wallDate(card.deadline, tz) : null,
        action_type_id: card.action_type_id,
      })
      remember({ id: crypto.randomUUID(), kind: 'backlog', title: card.title, link: '/inbox' })
      return
    }
    try {
      const t = await createTask.mutateAsync({
        title: card.title,
        task_type: card.task_type,
        description: card.description,
        subject_id: card.subject_id,
        action_type_id: card.action_type_id,
        deadline: card.deadline,
        priority: 'normal',
        subtasks: [],
      })
      setAi(null)
      if (breakDown) {
        navigate(`/tasks/${t.id}/breakdown`)
        return
      }
      remember({ id: t.id, kind: 'task', title: card.title, link: `/tasks/${t.id}` })
      toast.success('Задание добавлено', {
        action: { label: 'Открыть', onClick: () => navigate(`/tasks/${t.id}`) },
      })
    } catch {
      // Ошибку уже показал хук мутации; карточка остаётся
    }
  }

  const dateChip = () => {
    if (!live || !date) return null
    const time = live.time ? ` ${live.time}${live.end_time ? `–${live.end_time}` : ''}` : ''
    const prefix = kind === 'backlog' ? 'хорошо бы до ' : kind === 'task' && live.is_deadline ? 'до ' : ''
    return (
      <Chip icon={<CalendarIcon className="size-3" />} onRemove={() => setDropDate(true)}>
        {prefix}
        {formatDay(date)}
        {time}
      </Chip>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-3 py-4">
          <form
            className="flex items-start gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              void save()
            }}
          >
            <Textarea
              autoFocus
              rows={2}
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                if (!e.target.value.trim()) reset()
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void save()
                }
              }}
              enterKeyHint="send"
              placeholder={
                hasFiles
                  ? 'Что это: «реферат климатология до 15 окт» или тема конспекта'
                  : 'реферат климатология до 15 окт · купить продукты · завтра в 14 врач'
              }
              aria-label="Что добавить"
              className="min-h-14 resize-none text-base"
            />
            <Button
              type="submit"
              size="icon"
              className="size-11 shrink-0"
              aria-label="Добавить"
              disabled={uploading || aiParse.isPending || needsTime || (!text.trim() && !(hasFiles && (kind === 'note' || onlyImages)))}
            >
              {uploading || aiParse.isPending ? <Loader2Icon className="animate-spin" /> : <SendIcon />}
            </Button>
          </form>

          {hasFiles && <SharedFiles files={share.files} onRemove={share.removeFile} />}

          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            className="w-full"
            value={kind}
            onValueChange={(v) => v && setKindOverride(v as Kind)}
          >
            {KINDS.map(({ value, label, icon: Icon }) => (
              <ToggleGroupItem
                key={value}
                value={value}
                className="flex-1 gap-1"
                disabled={hasFiles && !FILE_KINDS.includes(value)}
              >
                <Icon className="size-4" />
                <span className="hidden sm:inline">{label}</span>
                <span className="sm:hidden">{label.replace('В ящик', 'Ящик')}</span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>

          {live && (
            <div className="flex flex-col gap-2" aria-live="polite">
              <div className="text-sm">
                <span className="text-muted-foreground">Название: </span>
                <span className="font-medium">{live.title || text.trim()}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {subject && kind !== 'backlog' && (
                  <Chip
                    icon={<span className={cn('size-2 rounded-full', paletteColor(subject.color).bg)} />}
                    onRemove={() => setDropSubject(true)}
                  >
                    {subject.short_name || subject.name}
                  </Chip>
                )}
                {dateChip()}
                {kind === 'event' && live.duration_min && !live.end_time && (
                  <Chip icon={<ClockIcon className="size-3" />}>{live.duration_min} мин</Chip>
                )}
                {kind === 'task' && live.task_type && (
                  <Chip icon={<BookOpenIcon className="size-3" />}>{TASK_TYPE_LABEL[live.task_type]}</Chip>
                )}
                {live.action_type && kind !== 'event' && (
                  <Chip>{actionTypes?.find((a) => a.key === live.action_type)?.name}</Chip>
                )}
              </div>
              {needsTime && <p className="text-xs text-destructive">Для события напишите время: «завтра в 14».</p>}
              {kind === 'task' && !hasFiles && live.needs_ai && (
                <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                  <SparklesIcon className="size-3.5 text-primary" />
                  {skipAi ? 'Сохраню как есть, без ИИ.' : 'ИИ уточнит предмет, тип и срок — вы проверите.'}
                  <button type="button" className="underline underline-offset-4" onClick={() => setSkipAi((v) => !v)}>
                    {skipAi ? 'с ИИ' : 'без ИИ'}
                  </button>
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {ai && (
        <AiParseCard
          key={ai.jobId}
          jobId={ai.jobId}
          busy={createTask.isPending}
          onCreate={(card, breakDown) => void createFromAi(card, breakDown)}
          onPlain={() => {
            createPlainTask(ai.raw, ai.p, ai.day, ai.subjectId)
            setAi(null)
          }}
          onClose={() => {
            setText(ai.raw)
            setAi(null)
          }}
        />
      )}

      <Button variant="outline" size="sm" className="self-start" onClick={() => setWorkTask(true)}>
        <BriefcaseIcon /> Задание с работы
      </Button>
      <WorkTaskDialog open={workTask} onOpenChange={setWorkTask} />

      {saved.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="px-2 text-xs text-muted-foreground uppercase">Только что</div>
          <ul>
            {saved.map((s) => (
              <li key={s.id}>
                <Link to={s.link ?? '#'} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-muted">
                  <CheckIcon className="size-4 text-emerald-500" />
                  <span className="truncate">{s.title}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {KINDS.find((k) => k.value === s.kind)?.label}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
