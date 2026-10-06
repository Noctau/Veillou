import {
  BookOpenIcon,
  BriefcaseIcon,
  CalendarIcon,
  CheckIcon,
  ClockIcon,
  InboxIcon,
  ListTodoIcon,
  NotebookPenIcon,
  SendIcon,
  XIcon,
} from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
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
import { formatDay, wallToUtc } from '@/lib/time'
import { cn } from '@/lib/utils'

import { type QuickParse, useParseNow, useQuickParse } from './useQuickParse'

type Kind = 'task' | 'backlog' | 'event' | 'note'

const KINDS: { value: Kind; label: string; icon: typeof InboxIcon }[] = [
  { value: 'task', label: 'Задание', icon: ListTodoIcon },
  { value: 'backlog', label: 'В ящик', icon: InboxIcon },
  { value: 'event', label: 'Событие', icon: CalendarIcon },
  { value: 'note', label: 'Конспект', icon: NotebookPenIcon },
]

const DEFAULT_EVENT_MIN = 60

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

  const { data: parsed } = useQuickParse(text)
  const parseNow = useParseNow()
  const { data: subjects } = useSubjects()
  const { data: actionTypes } = useActionTypes()
  const createTask = useCreateTask()
  const createBacklog = useCreateBacklog()
  const createEvent = useCreateEvent()
  const createNote = useCreateNote()

  const live = text.trim() ? parsed : undefined
  const kind: Kind = kindOverride ?? live?.kind_hint ?? 'backlog'
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
  }

  const remember = (item: Saved) => setSaved((old) => [item, ...old].slice(0, 5))

  const save = async () => {
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

    reset()
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
          remember({ id: t.id, kind, title, link: `/tasks/${t.id}` })
          toast.success('Задание добавлено', {
            action: { label: 'Открыть', onClick: () => navigate(`/tasks/${t.id}`) },
          })
        },
        onError: restore,
      },
    )
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
              placeholder="реферат климатология до 15 окт · купить продукты · завтра в 14 врач"
              aria-label="Что добавить"
              className="min-h-14 resize-none text-base"
            />
            <Button type="submit" size="icon" className="size-11 shrink-0" aria-label="Добавить" disabled={!text.trim() || needsTime}>
              <SendIcon />
            </Button>
          </form>

          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            className="w-full"
            value={kind}
            onValueChange={(v) => v && setKindOverride(v as Kind)}
          >
            {KINDS.map(({ value, label, icon: Icon }) => (
              <ToggleGroupItem key={value} value={value} className="flex-1 gap-1">
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
            </div>
          )}
        </CardContent>
      </Card>

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
