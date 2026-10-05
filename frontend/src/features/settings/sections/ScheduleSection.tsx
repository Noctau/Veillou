import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { TimeField, TimeRangeField } from '../fields'
import { SettingsSection } from '../SettingsSection'
import { useUpdateSettings, type UserSettings } from '../useSettings'
import { anyRange, intIn, wallTime } from '../zod'

const WEEKDAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

const schema = z.object({
  schedule: z.object({
    morning_digest: wallTime,
    evening_review: wallTime,
    weekly_review_weekday: intIn(1, 7),
    weekly_review: wallTime,
  }),
  quiet_hours: anyRange,
})

export function ScheduleSection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const form = useForm({
    resolver: zodResolver(schema),
    values: { schedule: settings.schedule, quiet_hours: settings.quiet_hours },
  })
  const { errors, isDirty } = form.formState
  const { register } = form

  return (
    <SettingsSection
      title="Сводка и разборы"
      onSubmit={form.handleSubmit((values) => update.mutate(values))}
      isDirty={isDirty}
      isSaving={update.isPending}
    >
      <TimeField
        id="morning_digest"
        label="Утренняя сводка"
        error={errors.schedule?.morning_digest?.message}
        {...register('schedule.morning_digest')}
      />
      <TimeField
        id="evening_review"
        label="Вечерний разбор"
        error={errors.schedule?.evening_review?.message}
        {...register('schedule.evening_review')}
      />
      <Field>
        <FieldLabel htmlFor="weekly_review_weekday">Недельный разбор</FieldLabel>
        <div className="flex items-center gap-2">
          <Controller
            control={form.control}
            name="schedule.weekly_review_weekday"
            render={({ field }) => (
              <Select value={String(field.value)} onValueChange={(v) => field.onChange(Number(v))}>
                <SelectTrigger id="weekly_review_weekday" className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WEEKDAYS.map((day, i) => (
                    <SelectItem key={day} value={String(i + 1)}>
                      {day}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <Input
            type="time"
            step={300}
            aria-label="Время недельного разбора"
            aria-invalid={!!errors.schedule?.weekly_review}
            {...register('schedule.weekly_review')}
          />
        </div>
        {errors.schedule?.weekly_review && (
          <FieldError>{errors.schedule.weekly_review.message}</FieldError>
        )}
      </Field>
      <TimeRangeField
        label="Тихие часы"
        description="Уведомления в это время откладываются до утра."
        start={register('quiet_hours.start')}
        end={register('quiet_hours.end')}
        error={errors.quiet_hours?.end?.message ?? errors.quiet_hours?.start?.message}
      />
    </SettingsSection>
  )
}
