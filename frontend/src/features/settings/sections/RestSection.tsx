import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { NumberField } from '../fields'
import { SettingsSection } from '../SettingsSection'
import { useUpdateSettings, type UserSettings } from '../useSettings'
import { intIn } from '../zod'

const schema = z.object({
  rest: z.object({
    free_evenings_per_week: intIn(0, 7),
    weekend_half_days: intIn(0, 4),
  }),
})

export function RestSection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const form = useForm({ resolver: zodResolver(schema), values: { rest: settings.rest } })
  const { errors, isDirty } = form.formState
  const num = { valueAsNumber: true } as const

  return (
    <SettingsSection
      title="Отдых"
      description="Минимум в неделю: сюда планировщик не поставит учёбу и дела."
      onSubmit={form.handleSubmit((values) => update.mutate(values))}
      isDirty={isDirty}
      isSaving={update.isPending}
    >
      <NumberField
        id="free_evenings_per_week"
        label="Свободных вечеров"
        suffix="в неделю"
        step={1}
        min={0}
        max={7}
        error={errors.rest?.free_evenings_per_week?.message}
        {...form.register('rest.free_evenings_per_week', num)}
      />
      <NumberField
        id="weekend_half_days"
        label="Свободных полдня в выходные"
        suffix="в неделю"
        step={1}
        min={0}
        max={4}
        error={errors.rest?.weekend_half_days?.message}
        {...form.register('rest.weekend_half_days', num)}
      />
    </SettingsSection>
  )
}
