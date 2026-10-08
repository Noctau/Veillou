import {
  CalendarRangeIcon,
  CheckIcon,
  CircleIcon,
  GraduationCapIcon,
  ListPlusIcon,
  MapPinIcon,
  PencilIcon,
  PlusIcon,
  RotateCwIcon,
  XIcon,
} from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { plural } from '@/features/plan/labels'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { formatMinutes } from '@/features/tasks/labels'
import { errorMessage } from '@/lib/errors'
import { formatDay, todayIn, wallDate, wallTime } from '@/lib/time'
import { cn } from '@/lib/utils'

import { ExamDialog } from './ExamDialog'
import {
  type Exam,
  type ExamDetail,
  type ExamQuestion,
  type ExamQuestionStatus,
  type ExamSession,
  useExam,
  useExamPlan,
  useExams,
  useImportQuestions,
  useUpdateQuestion,
} from './useExams'

const STATUS: Record<ExamQuestionStatus, { label: string; next: ExamQuestionStatus; icon: typeof CheckIcon; tone: string }> =
  {
    not_started: { label: 'не начат', next: 'learned', icon: CircleIcon, tone: 'text-muted-foreground' },
    learned: { label: 'выучен', next: 'review', icon: CheckIcon, tone: 'text-emerald-600 dark:text-emerald-400' },
    review: { label: 'повторить', next: 'not_started', icon: RotateCwIcon, tone: 'text-amber-600 dark:text-amber-400' },
  }

const SESSION_KIND: Record<ExamSession['kind'], string> = {
  learn: 'Выучить',
  review: 'Повторить',
  run: 'Общий прогон',
}

function daysLeft(exam: Exam, tz: string): number {
  const today = Date.parse(todayIn(tz))
  return Math.round((Date.parse(wallDate(exam.starts_at, tz)) - today) / 86_400_000)
}

/** Вставка списком: «1. …», «1) …» или по одному в строке. */
function ImportQuestions({ examId, onDone }: { examId: string; onDone?: () => void }) {
  const [text, setText] = useState('')
  const importQ = useImportQuestions()
  return (
    <div className="flex flex-col gap-2">
      <Textarea
        rows={6}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={'1. Уравнение состояния влажного воздуха\n2. Адиабатические процессы\n…'}
        aria-label="Вопросы списком"
      />
      <div className="flex justify-end gap-2">
        {onDone && (
          <Button variant="ghost" size="sm" onClick={onDone}>
            Отмена
          </Button>
        )}
        <Button
          size="sm"
          disabled={!text.trim() || importQ.isPending}
          onClick={() =>
            importQ.mutate(
              { id: examId, text },
              {
                onSuccess: () => {
                  setText('')
                  onDone?.()
                },
              },
            )
          }
        >
          <ListPlusIcon /> Добавить вопросы
        </Button>
      </div>
    </div>
  )
}

function QuestionRow({ q, examId }: { q: ExamQuestion; examId: string }) {
  const update = useUpdateQuestion(examId)
  const s = STATUS[q.status]
  const Icon = s.icon
  return (
    <li className="flex items-start gap-2 py-1.5">
      <span className="w-7 shrink-0 pt-0.5 text-right text-sm text-muted-foreground tabular-nums">{q.number}.</span>
      <span className="min-w-0 flex-1 text-sm">{q.text}</span>
      <Button
        variant="ghost"
        size="sm"
        className={cn('shrink-0 gap-1 px-2', s.tone)}
        aria-label={`Статус: ${s.label}. Сменить на «${STATUS[s.next].label}»`}
        onClick={() => update.mutate({ id: q.id, status: s.next })}
      >
        <Icon className="size-4" />
        <span className="text-xs">{s.label}</span>
      </Button>
    </li>
  )
}

function Questions({ exam }: { exam: ExamDetail }) {
  const [adding, setAdding] = useState(false)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Вопросы</CardTitle>
        {exam.questions.length > 0 && (
          <CardAction>
            <Button variant="ghost" size="sm" onClick={() => setAdding(true)}>
              <PlusIcon /> Ещё
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {exam.questions.length === 0 ? (
          <>
            <p className="text-sm text-muted-foreground">Вставьте список вопросов — нумерованный или по одному в строке.</p>
            <ImportQuestions examId={exam.id} />
          </>
        ) : (
          <>
            {adding && <ImportQuestions examId={exam.id} onDone={() => setAdding(false)} />}
            <p className="text-xs text-muted-foreground">Нажмите на статус: не начат → выучен → повторить.</p>
            <ul className="flex flex-col divide-y">
              {exam.questions.map((q) => (
                <QuestionRow key={q.id} q={q} examId={exam.id} />
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Plan({ exam }: { exam: ExamDetail }) {
  const tz = useTimeZone()
  const plan = useExamPlan()
  const byDay = new Map<string, ExamSession[]>()
  for (const s of exam.sessions) byDay.set(s.date, [...(byDay.get(s.date) ?? []), s])

  if (!exam.plan_enabled) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-3 py-4">
          <p className="text-sm text-muted-foreground">
            Вопросы распределятся по дням: за {exam.prep_days} {plural(exam.prep_days, 'день', 'дня', 'дней')} до экзамена —
            выучить, повторить через 1, 3 и 7 дней, накануне — общий прогон. Блоки встанут в свободные окна.
          </p>
          <Button
            disabled={!exam.questions.length || plan.isPending}
            onClick={() => plan.mutate({ id: exam.id, enable: true })}
          >
            <CalendarRangeIcon /> Построить план подготовки
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">План подготовки</CardTitle>
        <CardAction>
          <ConfirmButton
            title="Убрать план подготовки?"
            description="Будущие блоки подготовки уйдут из календаря после применения превью."
            confirmLabel="Убрать"
            onConfirm={() => plan.mutate({ id: exam.id, enable: false })}
          >
            <Button variant="ghost" size="sm">
              <XIcon /> Убрать
            </Button>
          </ConfirmButton>
        </CardAction>
      </CardHeader>
      <CardContent>
        {byDay.size === 0 ? (
          <p className="text-sm text-muted-foreground">Готовиться больше нечего — удачи на экзамене!</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {[...byDay.entries()].map(([day, sessions]) => (
              <li key={day} className="flex flex-col gap-1">
                <div className="text-sm font-medium first-letter:uppercase">{formatDay(day, { weekday: 'short' })}</div>
                {sessions.map((s) => (
                  <div key={s.id} className={cn('flex items-baseline gap-2 text-sm', s.status !== 'planned' && 'opacity-60')}>
                    <span className="min-w-0 flex-1">
                      <span className={cn(s.status === 'done' && 'line-through')}>{SESSION_KIND[s.kind]}</span>
                      {s.kind !== 'run' && <span className="text-muted-foreground"> №{s.numbers.join(', ')}</span>}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                      {s.status === 'done'
                        ? 'сделано'
                        : s.status === 'missed'
                          ? 'пропущено'
                          : s.start && s.end
                            ? `${wallTime(s.start, tz)}–${wallTime(s.end, tz)}`
                            : formatMinutes(s.minutes)}
                    </span>
                  </div>
                ))}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function ExamView({ examId, subjectId }: { examId: string; subjectId: string }) {
  const tz = useTimeZone()
  const { data: exam, isPending, isError, error } = useExam(examId)
  const [editing, setEditing] = useState(false)
  if (isPending) return <Skeleton className="h-48" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  const left = daysLeft(exam, tz)
  const total = exam.questions_total
  return (
    <div className="flex flex-col gap-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{exam.title}</CardTitle>
          <CardAction>
            <Button variant="ghost" size="icon" aria-label="Изменить экзамен" onClick={() => setEditing(true)}>
              <PencilIcon />
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="first-letter:uppercase">
              {formatDay(wallDate(exam.starts_at, tz), { weekday: 'short', month: 'long' })}, {wallTime(exam.starts_at, tz)}
            </span>
            {exam.location && (
              <span className="flex items-center gap-1">
                <MapPinIcon className="size-3.5" />
                {exam.location}
              </span>
            )}
            {left > 0 && <Badge variant="secondary">через {left} {plural(left, 'день', 'дня', 'дней')}</Badge>}
            {left === 0 && <Badge>сегодня</Badge>}
            {left < 0 && <Badge variant="outline">прошёл</Badge>}
          </div>
          {total > 0 && (
            <div className="flex items-center gap-3">
              <Progress value={(exam.questions_learned / total) * 100} className="h-2 flex-1" aria-label="Выучено" />
              <span className="text-xs text-muted-foreground tabular-nums">
                {exam.questions_learned} из {total}
              </span>
            </div>
          )}
        </CardContent>
      </Card>
      <Plan exam={exam} />
      <Questions exam={exam} />
      <ExamDialog subjectId={subjectId} exam={exam} open={editing} onOpenChange={setEditing} />
    </div>
  )
}

/** Вкладка «Экзамен» предмета: дата, билеты со статусами, план подготовки по дням (сценарий 8). */
export function ExamPanel({ subjectId, emptyHint }: { subjectId: string; emptyHint?: string }) {
  const { data: exams, isPending, isError, error } = useExams(subjectId)
  const [creating, setCreating] = useState(false)
  if (isPending) return <Skeleton className="h-32" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  return (
    <div className="flex flex-col gap-4">
      {exams.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
          <GraduationCapIcon className="size-8" />
          {emptyHint && <p className="text-foreground">{emptyHint}</p>}
          <p>Добавьте дату экзамена и вопросы — план подготовки построится по дням.</p>
          <Button className="mt-2" onClick={() => setCreating(true)}>
            <PlusIcon /> Добавить экзамен
          </Button>
        </div>
      ) : (
        <>
          {exams.map((e) => (
            <ExamView key={e.id} examId={e.id} subjectId={subjectId} />
          ))}
          <Button variant="ghost" size="sm" className="self-start" onClick={() => setCreating(true)}>
            <PlusIcon /> Ещё экзамен
          </Button>
        </>
      )}
      <ExamDialog subjectId={subjectId} open={creating} onOpenChange={setCreating} />
    </div>
  )
}
