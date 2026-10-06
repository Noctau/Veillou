import { ArrowLeftIcon, ExternalLinkIcon, GraduationCapIcon, PencilIcon, UserIcon } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { NoteList } from '@/features/notes/NoteList'
import { useSemesters } from '@/features/schedule/useSchedule'
import { SourceList } from '@/features/sources/SourceList'
import { TaskList } from '@/features/tasks/TaskList'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { formatDay } from '@/lib/time'
import { cn } from '@/lib/utils'

import { SubjectClasses } from './SubjectClasses'
import { SubjectDialog } from './SubjectDialog'
import { CONTROL_FORM_LABEL, type Subject, useSubjects } from './useSubjects'

const TABS = ['classes', 'notes', 'sources', 'tasks', 'exam'] as const
type Tab = (typeof TABS)[number]

function Header({ subject, onEdit }: { subject: Subject; onEdit: () => void }) {
  const navigate = useNavigate()
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-1">
        <Button variant="ghost" size="icon" aria-label="Назад" className="-ml-2 shrink-0" onClick={() => navigate(-1)}>
          <ArrowLeftIcon />
        </Button>
        <div className="flex min-w-0 flex-1 items-start gap-2 pt-0.5">
          <span className={cn('mt-2 size-3 shrink-0 rounded-full', paletteColor(subject.color).bg)} aria-hidden />
          <div className="min-w-0">
            <h1 className="text-2xl leading-tight font-semibold">{subject.name}</h1>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {subject.short_name && <span>{subject.short_name}</span>}
              {subject.control_form !== 'none' && <Badge variant="secondary">{CONTROL_FORM_LABEL[subject.control_form]}</Badge>}
            </div>
          </div>
        </div>
        <Button variant="ghost" size="icon" aria-label="Изменить предмет" onClick={onEdit}>
          <PencilIcon />
        </Button>
      </div>
      {(subject.teachers.length > 0 || subject.links.length > 0) && (
        <div className="flex flex-col gap-1 pl-9 text-sm">
          {subject.teachers.map((t, i) => (
            <span key={i} className="flex items-center gap-1.5 text-muted-foreground">
              <UserIcon className="size-3.5 shrink-0" />
              <span className="truncate">
                {t.name}
                {t.role && <span className="text-xs"> · {t.role}</span>}
                {t.contact && <span className="text-xs"> · {t.contact}</span>}
              </span>
            </span>
          ))}
          {subject.links.length > 0 && (
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {subject.links.map((l, i) => (
                <a
                  key={i}
                  href={l.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                >
                  {l.title || new URL(l.url).hostname}
                  <ExternalLinkIcon className="size-3" />
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Вкладка «Экзамен»: пока форма контроля и даты сессии; билеты и план подготовки — M12. */
function ExamTab({ subject }: { subject: Subject }) {
  const { data: semesters } = useSemesters()
  const semester = semesters?.find((s) => s.id === subject.semester_id)
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
      <GraduationCapIcon className="size-8" />
      <p className="text-foreground">
        {subject.control_form === 'none' ? 'Без итогового контроля' : CONTROL_FORM_LABEL[subject.control_form]}
      </p>
      {semester?.session_start && semester.session_end && (
        <p>
          Сессия: {formatDay(semester.session_start, { weekday: undefined, month: 'long' })} —{' '}
          {formatDay(semester.session_end, { weekday: undefined, month: 'long' })}
        </p>
      )}
      <p>Дата экзамена, билеты и план подготовки появятся в одном из следующих обновлений.</p>
    </div>
  )
}

/** Карточка предмета: всё по предмету в одном месте (сценарий 4). */
export function SubjectView({ subjectId }: { subjectId: string }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { data: subjects, isPending, isError, error } = useSubjects()
  const [editing, setEditing] = useState(false)
  const tab: Tab = TABS.find((t) => t === params.get('tab')) ?? 'classes'
  const subject = subjects?.find((s) => s.id === subjectId)

  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>
  if (!subject) return <p className="text-sm text-muted-foreground">Предмет не найден.</p>

  const setTab = (value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', value)
        return next
      },
      { replace: true },
    )

  return (
    <div className="flex flex-col gap-4">
      <Header subject={subject} onEdit={() => setEditing(true)} />

      <Tabs value={tab} onValueChange={setTab}>
        {/* 5 вкладок на 360 px не помещаются — прокрутка вбок */}
        <div className="-mx-4 overflow-x-auto px-4 [scrollbar-width:none]">
          <TabsList className="mb-3">
            <TabsTrigger value="classes">Пары</TabsTrigger>
            <TabsTrigger value="notes">Конспекты</TabsTrigger>
            <TabsTrigger value="sources">Литература</TabsTrigger>
            <TabsTrigger value="tasks">Задания</TabsTrigger>
            <TabsTrigger value="exam">Экзамен</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="classes">
          <SubjectClasses subject={subject} />
        </TabsContent>
        <TabsContent value="notes">
          <NoteList subjectId={subject.id} />
        </TabsContent>
        <TabsContent value="sources">
          <SourceList subjectId={subject.id} />
        </TabsContent>
        <TabsContent value="tasks">
          <TaskList subjectId={subject.id} />
        </TabsContent>
        <TabsContent value="exam">
          <ExamTab subject={subject} />
        </TabsContent>
      </Tabs>

      <SubjectDialog
        open={editing}
        onOpenChange={setEditing}
        subject={subject}
        onDeleted={() => navigate('/study', { replace: true })}
      />
    </div>
  )
}
