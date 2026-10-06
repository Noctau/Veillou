import { PageHeader } from '@/components/layout/PageHeader'
import { QuickAdd } from '@/features/quickadd/QuickAdd'

export function AddPage() {
  return (
    <>
      <PageHeader title="Быстрое добавление" />
      <QuickAdd />
    </>
  )
}
