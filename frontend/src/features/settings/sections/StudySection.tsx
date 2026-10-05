import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { NumberField } from '../fields'
import { SettingsSection } from '../SettingsSection'
import { useUpdateSettings, type UserSettings } from '../useSettings'
import { intIn } from '../zod'

const schema = z.object({
  study_limit_hours: z
    .number({ error: 'Введите число' })
    .min(0.5, 'Не меньше 0,5 ч')
    .max(16, 'Не больше 16 ч')
    .multipleOf(0.5, 'Шаг — полчаса'),
  travel_buffer_min: intIn(0, 240),
  deadline_buffer_days: intIn(0, 14),
})

export function StudySection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const form = useForm({
    resolver: zodResolver(schema),
    values: {
      study_limit_hours: settings.study_limit_min_per_day / 60,
      travel_buffer_min: settings.travel_buffer_min,
      deadline_buffer_days: settings.deadline_buffer_days,
    },
  })
  const { errors, isDirty } = form.formState
  const num = { valueAsNumber: true } as const

  return (
    <SettingsSection
      title="Учёба и сроки"
      onSubmit={form.handleSubmit(({ study_limit_hours, ...rest }) =>
        update.mutate({ ...rest, study_limit_min_per_day: Math.round(study_limit_hours * 60) }),
      )}
      isDirty={isDirty}
      isSaving={update.isPending}
    >
      <NumberField
        id="study_limit_hours"
        label="Лимит учёбы в день"
        suffix="ч"
        step={0.5}
        min={0.5}
        error={errors.study_limit_hours?.message}
        {...form.register('study_limit_hours', num)}
      />
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
