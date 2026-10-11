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

/** Подпись пустого значения справочника (тип задачи, тип действия). */
export const WITHOUT_TYPE = 'Без типа'

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
}

/** «Только в часы типа действия» (бывший чип «часы учреждений»). */
export const BACKLOG_HOURS = {
  label: 'Только в часы',
  any: 'В любое время',
  chip: (name: string) => `В часы: ${name}`,
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

// ---------- быстрые типы задач (M15.1) ----------

export const QUICK_TYPE = {
  description: (days: number) => `Срок — ${days} дн. с выдачи. Можно поменять.`,
  title: 'Что сделать',
  descriptionLabel: 'Описание',
  filesHint: 'Файлы можно приложить на экране задачи.',
  issued: 'Выдано',
  deadline: 'Срок',
  project: 'Проект',
  noProject: 'Без проекта',
  submit: 'Добавить',
  added: (name: string) => `${name}: добавлено`,
}

// ---------- справочники в Настройках (M15) ----------

export const ACTION_TYPES_UI = {
  title: 'Типы действий',
  description:
    'Когда уместно делать дела каждого типа. Окно типа важнее рабочих часов: читать можно и ночью, а звонить — только днём.',
  add: 'Тип действия',
  newTitle: 'Новый тип действия',
  name: 'Название',
  windows: 'Когда можно',
  windowsRequired: 'Нужно хотя бы одно окно.',
  category: 'Категория по умолчанию',
  noCategory: 'Без категории',
  morning: 'Лучше с утра',
  morningHint: 'План ставит такие дела пораньше в течение дня.',
  default: 'Тип по умолчанию',
  defaultHint: 'Для задач и дел, у которых тип не задан: окна, лимиты, утро.',
  noDefault: 'Без типа по умолчанию',
  reset: 'По умолчанию',
  deleteTitle: (name: string) => `Удалить «${name}»?`,
  deleteDescription: 'Задачи и дела этого типа получат тип по умолчанию, из лимитов тип уйдёт.',
  deleteLabel: 'Удалить тип действия',
  save: 'Сохранить',
  saving: 'Сохраняем…',
}

export const TASK_TYPES_UI = {
  title: 'Типы задач',
  description:
    'Тип подставляет умолчания новой задаче и отдельно калибрует оценки. Тип со сроком «через N дней» — быстрая кнопка в ＋.',
  empty: 'Типов задач пока нет — задачи создаются без типа.',
  add: 'Тип задачи',
  newTitle: 'Новый тип задачи',
  name: 'Название',
  icon: 'Иконка',
  synonyms: 'Слова для быстрого ввода',
  synonymsHint: 'Через запятую: «реферат, эссе». Помогают ИИ узнать тип.',
  more: 'Подробнее',
  less: 'Скрыть',
  actionType: 'Тип действия',
  category: 'Категория',
  estimate: 'Оценка, мин',
  deadlineDays: 'Срок через, дн.',
  deadlineHint: 'Пусто — срок не подставляется. С числом тип становится быстрой кнопкой.',
  project: 'Проект',
  template: 'Шаблон шагов',
  none: 'Не задан',
  deadlineChip: (days: number) => `срок +${days} дн.`,
  deleteTitle: (name: string) => `Удалить «${name}»?`,
  deleteDescription: 'Задачи этого типа останутся — без типа.',
  deleteLabel: 'Удалить тип задачи',
  save: 'Сохранить',
  saving: 'Сохраняем…',
}

export const BUDGETS_UI = {
  title: 'Лимиты',
  description:
    'Не больше N часов в день на группу дел. План не ставит сверх лимита; дела, которые в лимит не входят, он не ограничивает.',
  empty: 'Лимитов нет — план не ограничивает часы в день.',
  add: 'Лимит',
  newTitle: 'Новый лимит',
  name: 'Название',
  hours: 'Часов в день',
  members: 'Какие дела входят',
  membersHint: 'Типы действий, время которых идёт в лимит.',
  perDay: (hours: number) => `до ${hours} ч в день`,
  deleteTitle: (name: string) => `Удалить лимит «${name}»?`,
  deleteDescription: 'План перестанет ограничивать эти дела по часам.',
  deleteLabel: 'Удалить лимит',
  save: 'Сохранить',
  saving: 'Сохраняем…',
}
