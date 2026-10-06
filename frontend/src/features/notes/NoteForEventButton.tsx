import { NotebookPenIcon } from 'lucide-react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'

import { useNoteForEvent } from './useNotes'

type Props = {
  eventId: string
  /** У пары уже есть конспект — кнопка его откроет. */
  hasNote?: boolean
  size?: 'sm' | 'default'
  variant?: 'default' | 'outline' | 'secondary' | 'ghost'
  onDone?: () => void
  className?: string
  label?: string
}

/** «Конспект к этой паре»: открывает начатый конспект пары или создаёт новый с предметом и датой. */
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
      <NotebookPenIcon /> {label ?? (hasNote ? 'Открыть конспект' : 'Конспект к этой паре')}
    </Button>
  )
}
