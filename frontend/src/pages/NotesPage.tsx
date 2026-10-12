import { PageHeader } from '@/components/layout/PageHeader'
import { NoteList } from '@/features/notes/NoteList'
import { NAV_UI } from '@/lib/terms'

export function NotesPage() {
  return (
    <>
      <PageHeader title={NAV_UI.notes} />
      <NoteList showArea />
    </>
  )
}
