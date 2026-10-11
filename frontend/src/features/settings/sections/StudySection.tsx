import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { NumberField } from '../fields'
import { SettingsSection } from '../SettingsSection'
import { useUpdateSettings, type UserSettings } from '../useSettings'
import { intIn } from '../zod'

const schema = z.object({
  travel_buffer_min: intIn(0, 240),
  deadline_buffer_days: intIn(0, 14),
})

export function StudySection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const form = useForm({
    resolver: zodResolver(schema),
    values: {
      travel_buffer_min: settings.travel_buffer_min,
      deadline_buffer_days: settings.deadline_buffer_days,
    },
  })
  const { errors, isDirty } = form.formState
  const num = { valueAsNumber: true } as const

  return (
    <SettingsSection
      title="Дорога и сроки"
      onSubmit={form.handleSubmit((values) => update.mutate(values))}
      isDirty={isDirty}
      isSaving={update.isPending}
    >
      <NumberField
        id="travel_buffer_min"
        label="Дорога до университета"
        description="Время в пути в одну сторону — не занимается делами."
        suffix="мин"
        step={5}
        min={0}
        error={errors.travel_buffer_min?.message}
        {...form.register('travel_buffer_min', num)}
      />
      <NumberField
        id="deadline_buffer_days"
        label="Заканчивать до дедлайна за"
        suffix="дн."
        step={1}
        min={0}
        error={errors.deadline_buffer_days?.message}
        {...form.register('deadline_buffer_days', num)}
      />
    </SettingsSection>
  )
}
