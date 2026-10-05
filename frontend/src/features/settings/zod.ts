import { z } from 'zod'

export const wallTime = z
  .string({ error: 'Укажите время' })
  .regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Формат ЧЧ:ММ')

/** Интервал внутри дня (обед, рабочие часы). */
export const dayRange = z
  .object({ start: wallTime, end: wallTime })
  .refine((r) => r.end > r.start, { message: 'Конец должен быть позже начала', path: ['end'] })

/** Интервал, который может переходить через полночь (сон, тихие часы). */
export const anyRange = z.object({ start: wallTime, end: wallTime })

export const intIn = (min: number, max: number) =>
  z
    .number({ error: 'Введите число' })
    .int('Целое число')
    .min(min, `Не меньше ${min}`)
    .max(max, `Не больше ${max}`)
