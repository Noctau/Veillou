import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm, useWatch, type Control } from 'react-hook-form'
import { z } from 'zod'

import { Checkbox } from '@/components/ui/checkbox'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldSeparator,
} from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

import { NumberField } from '../fields'
import { SettingsSection } from '../SettingsSection'
import { useUpdateSettings, type UserSettings } from '../useSettings'
import { intIn } from '../zod'

const channel = z.enum(['push', 'telegram'])

const rule = z
  .object({ enabled: z.boolean(), channels: z.array(channel) })
  .refine((r) => !r.enabled || r.channels.length > 0, {
    message: 'Выберите хотя бы один канал',
    path: ['channels'],
  })

const schema = z.object({
  reminders: z.object({
    morning_digest: rule,
    before_class: z
      .object({ enabled: z.boolean(), channels: z.array(channel), minutes_before: intIn(0, 180) })
      .refine((r) => !r.enabled || r.channels.length > 0, {
        message: 'Выберите хотя бы один канал',
        path: ['channels'],
      }),
    deadlines: z
      .object({
        enabled: z.boolean(),
        channels: z.array(channel),
        days_before: z.array(z.number().int().min(0).max(14)),
      })
      .refine((r) => !r.enabled || r.channels.length > 0, {
        message: 'Выберите хотя бы один канал',
        path: ['channels'],
      })
      .refine((r) => !r.enabled || r.days_before.length > 0, {
        message: 'Выберите хотя бы один день',
        path: ['days_before'],
      }),
    evening_review: rule,
    weekly_review: rule,
    subtask_start: rule,
  }),
})

type FormValues = z.infer<typeof schema>
type RuleKey = keyof FormValues['reminders']

const RULES: { key: RuleKey; title: string; description: string }[] = [
  { key: 'morning_digest', title: 'Утренняя сводка', description: 'Пары, дела и дедлайны на день.' },
  { key: 'before_class', title: 'Перед парой', description: 'С аудиторией.' },
  { key: 'deadlines', title: 'Дедлайны', description: 'Во время утренней сводки, одним сообщением с ней.' },
  { key: 'evening_review', title: 'Вечерний разбор', description: 'Что сделано, что перенести.' },
  { key: 'weekly_review', title: 'Недельный разбор', description: 'Итоги недели и дела из ящика.' },
  { key: 'subtask_start', title: 'Начало подзадачи', description: 'Когда пора браться за дело.' },
]

const DEADLINE_DAYS = [
  { value: 7, label: 'за неделю' },
  { value: 3, label: 'за 3 дня' },
  { value: 2, label: 'за 2 дня' },
  { value: 1, label: 'за день' },
  { value: 0, label: 'в день сдачи' },
]

const CHANNELS = [
  { value: 'push', label: 'Push' },
  { value: 'telegram', label: 'Telegram' },
] as const

function ChannelPicker({ control, name }: { control: Control<FormValues>; name: RuleKey }) {
  const enabled = useWatch({ control, name: `reminders.${name}.enabled` })
  return (
    <Controller
      control={control}
      name={`reminders.${name}.channels`}
      render={({ field, fieldState }) => (
        <div className="flex flex-col gap-1">
          <div className="flex gap-4">
            {CHANNELS.map((ch) => {
              const id = `${name}-${ch.value}`
              return (
                <Field key={ch.value} orientation="horizontal" className="w-auto" data-disabled={!enabled}>
                  <Checkbox
                    id={id}
                    disabled={!enabled}
                    checked={field.value.includes(ch.value)}
                    onCheckedChange={(checked) =>
                      field.onChange(
                        checked
                          ? [...field.value, ch.value]
                          : field.value.filter((v) => v !== ch.value),
                      )
                    }
                  />
                  <FieldLabel htmlFor={id} className="font-normal">
                    {ch.label}
                  </FieldLabel>
                </Field>
              )
            })}
          </div>
          {fieldState.error && <FieldError>{fieldState.error.message}</FieldError>}
        </div>
      )}
    />
  )
}

export function RemindersSection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const form = useForm({ resolver: zodResolver(schema), values: { reminders: settings.reminders } })
  const { errors, isDirty } = form.formState
  const beforeClassEnabled = useWatch({ control: form.control, name: 'reminders.before_class.enabled' })
  const deadlinesEnabled = useWatch({ control: form.control, name: 'reminders.deadlines.enabled' })

  return (
    <SettingsSection
      title="Напоминания"
      description="Что присылать и куда."
      onSubmit={form.handleSubmit((values) => update.mutate(values))}
      isDirty={isDirty}
      isSaving={update.isPending}
    >
      {RULES.map((r, i) => (
        <div key={r.key} className="flex flex-col gap-3">
          {i > 0 && <FieldSeparator />}
          <Controller
            control={form.control}
            name={`reminders.${r.key}.enabled`}
            render={({ field }) => (
              <Field orientation="horizontal">
                <FieldContent>
                  <FieldLabel htmlFor={`${r.key}-enabled`}>{r.title}</FieldLabel>
                  <FieldDescription>{r.description}</FieldDescription>
                </FieldContent>
                <Switch id={`${r.key}-enabled`} checked={field.value} onCheckedChange={field.onChange} />
              </Field>
            )}
          />
          <ChannelPicker control={form.control} name={r.key} />
          {r.key === 'deadlines' && (
            <Controller
              control={form.control}
              name="reminders.deadlines.days_before"
              render={({ field, fieldState }) => (
                <div className="flex flex-col gap-1">
                  <ToggleGroup
                    type="multiple"
                    variant="outline"
                    size="sm"
                    className="flex-wrap justify-start"
                    disabled={!deadlinesEnabled}
                    value={field.value.map(String)}
                    onValueChange={(v) => field.onChange(v.map(Number).sort((a, b) => b - a))}
                  >
                    {DEADLINE_DAYS.map((d) => (
                      <ToggleGroupItem key={d.value} value={String(d.value)} className="rounded-full! border px-3">
                        {d.label}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                  {fieldState.error && <FieldError>{fieldState.error.message}</FieldError>}
                </div>
              )}
            />
          )}
          {r.key === 'before_class' && (
            <NumberField
              id="minutes_before"
              label="За сколько до пары"
              suffix="мин"
              step={5}
              min={0}
              disabled={!beforeClassEnabled}
              error={errors.reminders?.before_class?.minutes_before?.message}
              {...form.register('reminders.before_class.minutes_before', { valueAsNumber: true })}
            />
          )}
        </div>
      ))}
    </SettingsSection>
  )
}
