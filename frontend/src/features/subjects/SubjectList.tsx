import { ExternalLinkIcon, PlusIcon, UserIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import { SubjectDialog } from './SubjectDialog'
import { CONTROL_FORM_LABEL, type Subject, useSubjects } from './useSubjects'

function SubjectCard({ subject }: { subject: Subject }) {
  const color = paletteColor(subject.color)
  return (
    <Card className="relative overflow-hidden py-0">
      <span className={cn('absolute inset-y-0 left-0 w-1.5', color.bg)} aria-hidden />
      <CardContent className="flex flex-col gap-2 py-3 pl-5">
        <Link to={`/subjects/${subject.id}`} className="flex items-start gap-2 text-left after:absolute after:inset-0">
          <span className="flex-1">
            <span className="block font-medium leading-tight">{subject.name}</span>
            {subject.short_name && (
              <span className="text-xs text-muted-foreground">{subject.short_name}</span>
            )}
          </span>
          {subject.control_form !== 'none' && (
            <Badge variant="secondary">{CONTROL_FORM_LABEL[subject.control_form]}</Badge>
          )}
        </Link>
        {subject.teachers.length > 0 && (
          <ul className="flex flex-col gap-0.5 text-sm text-muted-foreground">
            {subject.teachers.map((t, i) => (
              <li key={i} className="flex items-center gap-1.5">
                <UserIcon className="size-3.5 shrink-0" />
                <span className="truncate">
                  {t.name}
                  {t.role && <span className="text-xs"> · {t.role}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
        {subject.links.length > 0 && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
            {subject.links.map((l, i) => (
              <a
                key={i}
                href={l.url}
                target="_blank"
                rel="noreferrer"
                className="relative z-10 inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
              >
                {l.title || new URL(l.url).hostname}
                <ExternalLinkIcon className="size-3" />
              </a>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function SubjectList({ semesterId }: { semesterId?: string }) {
  const { data, isPending, isError, error } = useSubjects()
  const [creating, setCreating] = useState(false)

  const subjects = (data ?? []).filter((s) => !semesterId || s.semester_id === semesterId || !s.semester_id)

  return (
    <div className="flex flex-col gap-3">
      {isPending && <Skeleton className="h-24" />}
      {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
      {data && subjects.length === 0 && (
        <p className="py-6 text-center text-sm text-muted-foreground">
          Пока нет предметов. Добавьте первый — или сразу вбивайте пары во вкладке «Расписание».
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {subjects.map((s) => (
          <SubjectCard key={s.id} subject={s} />
        ))}
      </div>
      <Button variant="outline" className="self-start" onClick={() => setCreating(true)}>
        <PlusIcon /> Предмет
      </Button>

      <SubjectDialog
        open={creating}
        onOpenChange={setCreating}
        semesterId={semesterId}
        colorIndex={data?.length ?? 0}
      />
    </div>
  )
}
