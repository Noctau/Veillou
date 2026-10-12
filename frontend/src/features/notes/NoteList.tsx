import { BookIcon, PaperclipIcon, PlusIcon, SearchIcon, XIcon } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { useAreas } from '@/features/areas/useAreas'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { formatDay } from '@/lib/time'
import { cn } from '@/lib/utils'

import { Highlight } from './Highlight'
import { NOTE_KIND, NOTE_KINDS } from './labels'
import { useSearch } from './useSearch'
import { type NoteCreate, type NoteListItem, useCreateNote, useNotes } from './useNotes'

/** «＋ Заметка» → вид → сразу открыть новую заметку. */
export function NewNoteButton({ draft = {}, size = 'sm' }: { draft?: Partial<NoteCreate>; size?: 'sm' | 'default' }) {
  const navigate = useNavigate()
  const create = useCreateNote()
  const start = (kind: NoteCreate['kind']) =>
    create.mutate({ body_md: '', ...draft, kind }, { onSuccess: (note) => navigate(`/notes/${note.id}`) })
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size={size} variant="ghost" disabled={create.isPending}>
          <PlusIcon /> Заметка
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

export function NoteRow({ note, showArea, snippet }: { note: NoteListItem; showArea?: boolean; snippet?: ReactNode }) {
  const { data: areas } = useAreas()
  const area = showArea && note.area_id ? areas?.find((s) => s.id === note.area_id) : undefined
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
          {area && (
            <>
              <span className={cn('size-2 shrink-0 rounded-full', paletteColor(area.color).bg)} />
              <span className="truncate">{area.short_name || area.name}</span>
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
  areaId?: string
  /** Показывать сферу у каждой заметки (общий список). */
  showArea?: boolean
  limit?: number
}

function SearchResultsList({ text, areaId, showArea }: { text: string; areaId?: string; showArea?: boolean }) {
  const { data, isPending, isError, error, isPlaceholderData } = useSearch(text, areaId)
  const { data: areas } = useAreas()
  if (isPending) return <Skeleton className="h-24" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>
  if (!data.notes.length && !data.sources.length) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Ничего не нашлось.</p>
  }
  return (
    <div className={cn('flex flex-col gap-4', isPlaceholderData && 'opacity-60')}>
      {data.notes.length > 0 && (
        <ul className="flex flex-col gap-1">
          {data.notes.map((n) => (
            <li key={n.id}>
              <NoteRow note={n} showArea={showArea} snippet={n.snippet ? <Highlight text={n.snippet} /> : undefined} />
            </li>
          ))}
        </ul>
      )}
      {data.sources.length > 0 && (
        <section className="flex flex-col gap-1">
          <h3 className="px-1 text-xs text-muted-foreground uppercase">Литература</h3>
          <ul className="flex flex-col gap-1">
            {data.sources.map((s) => {
              const area = areas?.find((x) => x.id === s.area_id)
              return (
                <li key={s.id}>
                  <Link
                    to={`/areas/${s.area_id}?tab=sources`}
                    className="flex items-center gap-3 rounded-lg border px-3 py-2.5 hover:bg-muted"
                  >
                    <BookIcon className="size-5 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{s.title}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {[s.author, showArea && area && (area.short_name || area.name)].filter(Boolean).join(' · ')}
                      </div>
                    </div>
                  </Link>
                </li>
              )
            })}
          </ul>
        </section>
      )}
    </div>
  )
}

/** Заметки сферы (или все): свежие первыми. */
export function NoteList({ areaId, showArea, limit }: Props) {
  const [text, setText] = useState('')
  const searching = text.trim().length > 0
  const { data: notes, isPending, isError, error } = useNotes({ area_id: areaId, limit })
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Поиск по заметкам и материалам"
            aria-label="Поиск по заметкам"
            className="pr-8 pl-8 [&::-webkit-search-cancel-button]:hidden"
          />
          {searching && (
            <button
              type="button"
              aria-label="Очистить поиск"
              onClick={() => setText('')}
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full p-0.5 text-muted-foreground hover:bg-muted"
            >
              <XIcon className="size-4" />
            </button>
          )}
        </div>
        <NewNoteButton draft={{ area_id: areaId ?? null }} />
      </div>
      {searching ? (
        <SearchResultsList text={text} areaId={areaId} showArea={showArea} />
      ) : (
        <>
          {isPending && <Skeleton className="h-24" />}
          {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
          {notes && notes.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Заметок пока нет. Текст с формулами, фото страниц, PDF или ссылка на Диск.
            </p>
          )}
          <ul className="flex flex-col gap-1">
            {notes?.map((n) => (
              <li key={n.id}>
                <NoteRow note={n} showArea={showArea} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
