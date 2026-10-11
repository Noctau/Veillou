/**
 * Лексика интерфейса в одном месте (Part 2, M14.3).
 *
 * Сюда собраны словари меток из фич — чтобы вычитывать формулировки (M22.3) и
 * переводить (i18n) в одном файле. Названия кирпичей (сферы, типы занятости,
 * типы задач после M15) сюда не попадают: они приходят из данных пользователя.
 * Формулировки — нейтральные, без рода.
 */
import type { components } from '@/api/schema'

type Schemas = components['schemas']

// ---------- задания ----------

export const TASK_TYPE_LABEL: Record<Schemas['TaskType'], string> = {
  homework: 'ДЗ',
  report: 'Доклад',
  essay: 'Реферат',
  lab: 'Лабораторная',
  coursework: 'Курсовая',
  reading: 'Чтение',
  exam_prep: 'К экзамену',
  other: 'Другое',
}

export const PRIORITY_LABEL: Record<Schemas['Priority'], string> = { normal: 'Обычная', high: 'Высокая' }

export const FEEL_LABEL: Record<Schemas['Feel'], string> = {
  faster: 'Быстрее',
  ok: 'Как планировалось',
  slower: 'Дольше',
}

// ---------- календарь ----------

export const KIND_LABEL: Record<Schemas['EventKind'], string> = {
  class: 'Пары',
  personal: 'Личное',
  rest: 'Отдых',
  subtask: 'Задания',
  backlog: 'Ящик',
  exam_prep: 'Подготовка',
  exam: 'Экзамены',
  project: 'Проекты',
}

/** Тип одного события — для карточки. */
export const KIND_SINGLE: Record<Schemas['EventKind'], string> = {
  class: 'Пара',
  personal: 'Личное',
  rest: 'Отдых',
  subtask: 'Подзадача',
  backlog: 'Дело из ящика',
  exam_prep: 'Подготовка к экзамену',
  exam: 'Экзамен',
  project: 'Работа над проектом',
}

// ---------- расписание и предметы ----------

export const PARITY_LABEL: Record<Schemas['Parity'], string> = { odd: 'Числитель', even: 'Знаменатель' }

export const RULE_PARITY_LABEL: Record<Schemas['RuleParity'], string> = {
  all: 'Каждую неделю',
  odd: 'Числитель',
  even: 'Знаменатель',
}

export const CLASS_TYPE_LABEL: Record<Schemas['ClassType'], string> = {
  lecture: 'Лекция',
  seminar: 'Семинар',
  lab: 'Лаба',
  other: 'Другое',
}

export const CONTROL_FORM_LABEL: Record<Schemas['ControlForm'], string> = {
  exam: 'Экзамен',
  credit: 'Зачёт',
  graded_credit: 'Дифзачёт',
  coursework: 'Курсовая',
  none: 'Без контроля',
}

// ---------- долгий ящик ----------

export const CONDITION_LABEL: Record<Schemas['BacklogCondition'], string> = {
  weekday_daytime: 'В будни днём',
  on_class_days: 'В дни пар',
  needs_laptop: 'Нужен ноутбук',
  institution_hours: 'Часы учреждений',
}

// ---------- план ----------

export const RISK_LABEL: Record<Schemas['RiskReason'], string> = {
  no_slots: 'нет подходящего времени до дедлайна',
  no_time: 'не хватает времени до дедлайна',
  dependency: 'не поставлен предыдущий шаг',
  late: 'позже, чем хотелось (впритык к дедлайну)',
  overdue: 'дедлайн уже прошёл',
  rest: 'влезет, только если отдать минимум отдыха',
  quota: 'не набирается недельная норма',
}

export const REASON_LABEL: Record<Schemas['PlanReason'], string> = {
  manual: 'Перепланировали',
  changes: 'План устарел после правок',
  missed: 'Переносим невыполненное',
  nightly: 'Пересчитали план за ночь',
  weekly: 'Дела из ящика на неделю',
  exam: 'План подготовки к экзамену',
}

// ---------- конспекты ----------

export const NOTE_KIND_LABEL: Record<Schemas['NoteKind'], string> = {
  text: 'Текст',
  photo: 'Фото',
  file: 'Файл',
  link: 'Ссылка',
}

// ---------- напоминания (Настройки) ----------

/** Порядок ключей — порядок строк в Настройках. */
export const REMINDER_LABEL: Record<keyof Schemas['Reminders'], { title: string; description: string }> = {
  morning_digest: { title: 'Утренняя сводка', description: 'Пары, дела и дедлайны на день.' },
  before_class: { title: 'Перед парой', description: 'С аудиторией.' },
  deadlines: { title: 'Дедлайны', description: 'Во время утренней сводки, одним сообщением с ней.' },
  evening_review: { title: 'Вечерний разбор', description: 'Что сделано, что перенести.' },
  weekly_review: { title: 'Недельный разбор', description: 'Итоги недели и дела из ящика.' },
  subtask_start: { title: 'Начало подзадачи', description: 'Когда пора браться за дело.' },
}
