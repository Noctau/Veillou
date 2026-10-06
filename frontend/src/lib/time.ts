import { addDays, format, parseISO } from 'date-fns'
import { formatInTimeZone, fromZonedTime } from 'date-fns-tz'

/** ISO-день недели (1 = Пн) по дате 'YYYY-MM-DD'. */
export function isoWeekday(day: string): number {
  const wd = parseISO(day).getDay()
  return wd === 0 ? 7 : wd
}

/** Сегодняшняя дата в TZ пользователя, 'YYYY-MM-DD'. */
export function todayIn(timeZone: string, now: Date = new Date()): string {
  return formatInTimeZone(now, timeZone, 'yyyy-MM-dd')
}

export function addDaysIso(day: string, n: number): string {
  return format(addDays(parseISO(day), n), 'yyyy-MM-dd')
}

/** Понедельник недели, в которую попадает день. */
export function weekMonday(day: string): string {
  return addDaysIso(day, 1 - isoWeekday(day))
}

/** Начало локального дня `day` в TZ — момент (ISO с Z). */
export function dayStartUtc(day: string, timeZone: string): string {
  return fromZonedTime(`${day}T00:00:00`, timeZone).toISOString()
}

/** Момент → настенное время 'HH:mm' в TZ. */
export function wallTime(iso: string, timeZone: string): string {
  return formatInTimeZone(parseISO(iso), timeZone, 'HH:mm')
}

/** Момент → локальная дата 'YYYY-MM-DD' в TZ. */
export function wallDate(iso: string, timeZone: string): string {
  return formatInTimeZone(parseISO(iso), timeZone, 'yyyy-MM-dd')
}

/** Настенные дата+время в TZ → момент (ISO с Z). */
export function wallToUtc(day: string, time: string, timeZone: string): string {
  return fromZonedTime(`${day}T${time}:00`, timeZone).toISOString()
}

/** Момент → «наивная» строка 'YYYY-MM-DDTHH:mm:ss' настенного времени в TZ. */
export function toWallIso(iso: string | Date, timeZone: string): string {
  return formatInTimeZone(iso, timeZone, "yyyy-MM-dd'T'HH:mm:ss")
}

/** 'YYYY-MM-DD' → «7 окт., вт» */
export function formatDay(day: string, options: Intl.DateTimeFormatOptions = {}): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    weekday: 'short',
    ...options,
  }).format(parseISO(day))
}

export const WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
export const WEEKDAYS_FULL = [
  'Понедельник',
  'Вторник',
  'Среда',
  'Четверг',
  'Пятница',
  'Суббота',
  'Воскресенье',
]
