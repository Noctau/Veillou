import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { TimeRangeField } from '../fields'
import { SettingsSection } from '../SettingsSection'
import { useUpdateSettings, type UserSettings } from '../useSettings'
import { anyRange, dayRange } from '../zod'

const schema = z.object({
  work_hours: z.object({ weekdays: dayRange, weekends: dayRange }),
  lunch: dayRange,
  sleep: anyRange,
})

export function DayModeSection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const form = useForm({
    resolver: zodResolver(schema),
    values: { work_hours: settings.work_hours, lunch: settings.lunch, sleep: settings.sleep },
  })
  const { errors, isDirty } = form.formState
  const { register } = form

  return (
    <SettingsSection
      title="Режим дня"
      description="В это время можно ставить учёбу и дела."
      onSubmit={form.handleSubmit((values) => update.mutate(values))}
      isDirty={isDirty}
      isSaving={update.isPending}
    >
      <TimeRangeField
        label="Рабочие часы в будни"
        start={register('work_hours.weekdays.start')}
        end={register('work_hours.weekdays.end')}
        error={errors.work_hours?.weekdays?.end?.message ?? errors.work_hours?.weekdays?.start?.message}
      />
      <TimeRangeField
        label="Рабочие часы в выходные"
        start={register('work_hours.weekends.start')}
        end={register('work_hours.weekends.end')}
        error={errors.work_hours?.weekends?.end?.message ?? errors.work_hours?.weekends?.start?.message}
      />
      <TimeRangeField
        label="Обед"
        start={register('lunch.start')}
        end={register('lunch.end')}
        error={errors.lunch?.end?.message ?? errors.lunch?.start?.message}
      />
      <TimeRangeField
        label="Сон"
        description="Можно через полночь, например 23:30 — 07:30."
        start={register('sleep.start')}
        end={register('sleep.end')}
        error={errors.sleep?.end?.message ?? errors.sleep?.start?.message}
      />
    </SettingsSection>
  )
}
