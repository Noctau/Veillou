import { NotebookPenIcon } from 'lucide-react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'

import { useNoteForEvent } from './useNotes'

type Props = {
  eventId: string
  /** У события уже есть заметка — кнопка её откроет. */
  hasNote?: boolean
  size?: 'sm' | 'default'
  variant?: 'default' | 'outline' | 'secondary' | 'ghost'
  onDone?: () => void
  className?: string
  label?: string
}

/** «Заметка к событию»: открывает начатую заметку события или создаёт новую со сферой и датой. */
export function NoteForEventButton({ eventId, hasNote, size = 'sm', variant = 'outline', onDone, className, label }: Props) {
  const navigate = useNavigate()
  const open = useNoteForEvent()
  return (
    <Button
      size={size}
      variant={variant}
      className={className}
      disabled={open.isPending}
      onClick={() =>
        open.mutate(
          { eventId },
          {
            onSuccess: (note) => {
              onDone?.()
              navigate(`/notes/${note.id}`)
            },
          },
        )
      }
    >
      <NotebookPenIcon /> {label ?? (hasNote ? 'Открыть заметку' : 'Заметка к событию')}
    </Button>
  )
}
