import { PaperclipIcon, PlusIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { useSubjects } from '@/features/subjects/useSubjects'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { formatDay } from '@/lib/time'
import { cn } from '@/lib/utils'

import { NOTE_KIND, NOTE_KINDS } from './labels'
import { type NoteCreate, type NoteListItem, useCreateNote, useNotes } from './useNotes'

/** «＋ Конспект» → вид → сразу открыть новый конспект. */
export function NewNoteButton({ draft = {}, size = 'sm' }: { draft?: Partial<NoteCreate>; size?: 'sm' | 'default' }) {
  const navigate = useNavigate()
  const create = useCreateNote()
  const start = (kind: NoteCreate['kind']) =>
    create.mutate({ body_md: '', ...draft, kind }, { onSuccess: (note) => navigate(`/notes/${note.id}`) })
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size={size} variant="ghost" disabled={create.isPending}>
          <PlusIcon /> Конспект
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {NOTE_KINDS.map((kind) => {
          const { label, icon: Icon } = NOTE_KIND[kind]
          return (
            <DropdownMenuItem key={kind} onSelect={() => start(kind)}>
              <Icon /> {label}
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function NoteRow({ note, showSubject, snippet }: { note: NoteListItem; showSubject?: boolean; snippet?: ReactNode }) {
  const { data: subjects } = useSubjects()
  const subject = showSubject && note.subject_id ? subjects?.find((s) => s.id === note.subject_id) : undefined
  const Icon = NOTE_KIND[note.kind].icon
  return (
    <Link to={`/notes/${note.id}`} className="flex items-center gap-3 rounded-lg border px-3 py-2.5 hover:bg-muted">
      {note.cover_url ? (
        <img src={note.cover_url} alt="" loading="lazy" className="size-11 shrink-0 rounded-md border object-cover" />
      ) : (
        <span className="flex size-11 shrink-0 items-center justify-center rounded-md bg-muted">
          <Icon className="size-5 text-muted-foreground" />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{note.title}</div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {subject && (
            <>
              <span className={cn('size-2 shrink-0 rounded-full', paletteColor(subject.color).bg)} />
              <span className="truncate">{subject.short_name || subject.name}</span>
              {note.class_date && <span>·</span>}
            </>
          )}
          {note.class_date && <span className="whitespace-nowrap">{formatDay(note.class_date)}</span>}
          {note.attachments_count > 0 && (
            <span className="flex items-center gap-0.5 whitespace-nowrap">
              · <PaperclipIcon className="size-3" />
              {note.attachments_count}
            </span>
          )}
        </div>
        {(snippet ?? note.excerpt) && (
          <div className="line-clamp-2 text-xs text-muted-foreground">{snippet ?? note.excerpt}</div>
        )}
      </div>
    </Link>
  )
}

type Props = {
  subjectId?: string
  /** Показывать предмет у каждого конспекта (общий список). */
  showSubject?: boolean
  limit?: number
}

/** Конспекты предмета (или все): свежие пары первыми. */
export function NoteList({ subjectId, showSubject, limit }: Props) {
  const { data: notes, isPending, isError, error } = useNotes({ subject_id: subjectId, limit })
  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <NewNoteButton draft={{ subject_id: subjectId ?? null }} />
      </div>
      {isPending && <Skeleton className="h-24" />}
      {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
      {notes && notes.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Конспектов пока нет. Текст с формулами, фото тетради, PDF или ссылка на Диск.
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {notes?.map((n) => (
          <li key={n.id}>
            <NoteRow note={n} showSubject={showSubject} />
          </li>
        ))}
      </ul>
    </div>
  )
}
