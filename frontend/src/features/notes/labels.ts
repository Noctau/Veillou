import { FileTextIcon, ImageIcon, LinkIcon, NotebookPenIcon } from 'lucide-react'

import type { Attachment } from '@/features/attachments/useAttachments'
import { CLASS_TYPE_LABEL, NOTE_KIND_LABEL } from '@/lib/terms'
import { wallTime } from '@/lib/time'

import type { Note, NoteKind } from './useNotes'

export const NOTE_KIND: Record<NoteKind, { label: string; icon: typeof ImageIcon }> = {
  text: { label: NOTE_KIND_LABEL.text, icon: NotebookPenIcon },
  photo: { label: NOTE_KIND_LABEL.photo, icon: ImageIcon },
  file: { label: NOTE_KIND_LABEL.file, icon: FileTextIcon },
  link: { label: NOTE_KIND_LABEL.link, icon: LinkIcon },
}

export const NOTE_KINDS = Object.keys(NOTE_KIND) as NoteKind[]

/** Картинка, которую покажет <img>. HEIC браузеры (кроме Safari) не умеют — это «файл». */
export const isPageImage = (a: Pick<Attachment, 'mime'>) => /^image\/(png|jpeg|webp|gif)$/.test(a.mime)

/** «2 пара · 09:00–10:35 · Семинар · 1801» */
export function pairLabel(event: NonNullable<Note['event']>, tz: string): string {
  return [
    event.pair_number && `${event.pair_number} пара`,
    `${wallTime(event.start, tz)}–${wallTime(event.end, tz)}`,
    event.class_type && CLASS_TYPE_LABEL[event.class_type],
    event.location,
  ]
    .filter(Boolean)
    .join(' · ')
}
