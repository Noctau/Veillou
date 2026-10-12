import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { NumberField } from '../fields'
import { SettingsSection } from '../SettingsSection'
import { useUpdateSettings, type UserSettings } from '../useSettings'
import { intIn } from '../zod'

const schema = z.object({ deadline_buffer_days: intIn(0, 14) })

/** Запас до дедлайна. Дорога — у типов занятости (M17). */
export function StudySection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const form = useForm({
    resolver: zodResolver(schema),
    values: { deadline_buffer_days: settings.deadline_buffer_days },
  })
  const { errors, isDirty } = form.formState

  return (
    <SettingsSection
      title="Сроки"
      onSubmit={form.handleSubmit((values) => update.mutate(values))}
      isDirty={isDirty}
      isSaving={update.isPending}
    >
      <NumberField
        id="deadline_buffer_days"
        label="Заканчивать до дедлайна за"
        suffix="дн."
        step={1}
        min={0}
        error={errors.deadline_buffer_days?.message}
        {...form.register('deadline_buffer_days', { valueAsNumber: true })}
      />
    </SettingsSection>
  )
}
