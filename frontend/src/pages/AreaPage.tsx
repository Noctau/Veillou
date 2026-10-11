import { useParams } from 'react-router'

import { AreaView } from '@/features/areas/AreaView'

export function AreaPage() {
  const { areaId } = useParams()
  return <AreaView key={areaId} areaId={areaId!} />
}
