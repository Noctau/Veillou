import { useNavigate } from 'react-router'

import { PageHeader } from '@/components/layout/PageHeader'
import { SetupFlow } from '@/features/setup/SetupFlow'
import { SETUP_UI } from '@/lib/terms'

export function SetupPage() {
  const navigate = useNavigate()
  return (
    <>
      <PageHeader title={SETUP_UI.title} />
      <SetupFlow onApplied={() => navigate('/settings?tab=catalog')} />
    </>
  )
}
