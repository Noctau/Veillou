import { useParams } from 'react-router'

import { NoteView } from '@/features/notes/NoteView'

export function NotePage() {
  const { noteId } = useParams()
  return <NoteView key={noteId} noteId={noteId!} />
}
