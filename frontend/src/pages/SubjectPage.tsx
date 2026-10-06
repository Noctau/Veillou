import { useParams } from 'react-router'

import { SubjectView } from '@/features/subjects/SubjectView'

export function SubjectPage() {
  const { subjectId } = useParams()
  return <SubjectView key={subjectId} subjectId={subjectId!} />
}
