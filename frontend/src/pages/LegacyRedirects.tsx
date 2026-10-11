import { Navigate, useLocation, useParams } from 'react-router'

/** Старые адреса Part 1 (ссылки в пушах, закладки): «Учёба» → «Сферы». */
export function StudyRedirect() {
  const { search } = useLocation()
  return <Navigate to={`/areas${search}`} replace />
}

export function SubjectRedirect() {
  const { subjectId } = useParams()
  const { search } = useLocation()
  return <Navigate to={`/areas/${subjectId}${search}`} replace />
}
