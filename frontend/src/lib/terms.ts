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

/** Слои блоков плана; жёсткие события (busy) — слоями по типам занятости из данных. */
export const KIND_LABEL: Record<Schemas['EventKind'], string> = {
  busy: 'Занятость',
  subtask: 'Задачи',
  backlog: 'Ящик',
  prep: 'Подготовка',
  project: 'Проекты',
}

/** Тип одного события — для карточки (у жёсткого — название типа занятости). */
export const KIND_SINGLE: Record<Schemas['EventKind'], string> = {
  busy: 'Событие',
  subtask: 'Шаг задачи',
  backlog: 'Дело из ящика',
  prep: 'Подготовка',
  project: 'Работа над проектом',
}

/** Слой событий без типа занятости. */
export const UNTYPED_LAYER = 'Без типа'

// ---------- расписание (M17) ----------

export const PATTERN_LABEL: Record<Schemas['ScheduleRuleRead']['pattern']['kind'], string> = {
  weekly: 'По дням недели',
  day_cycle: 'Смены N через M',
  once: 'Разово',
  rrule: 'RRULE',
}

export const CHANNEL_LABEL: Record<Schemas['Channel'], string> = { push: 'Push', telegram: 'Telegram' }

export const SCHEDULE_UI = {
  title: 'Расписание',
  noPeriod: 'Без периода',
  noPeriodHint: 'Правила без периода повторяются всегда (на 90 дней вперёд, окно докатывается).',
  period: 'Период',
  newPeriod: 'Период',
  newPeriodTitle: 'Новый период',
  periodSettings: 'Настройки периода',
  periodCreated: 'Период создан',
  saved: 'Сохранено',
  startTitle: 'Начнём с правил',
  startHint:
    'Правило — «что и когда повторяется»: урок по вторникам, смена 2/2, стандап по будням. Период нужен, если есть границы и цикл недель (семестр, четверть).',
  cycleWeek: (n: number) => `Неделя ${n}`,
  currentCycleWeek: (n: number) => `сейчас неделя ${n}`,
  everyWeek: 'Каждую неделю',
  weeks: 'Недели цикла',
  slots: 'Слоты',
  slotsHint: 'Сетка слотов — номера и время (звонки, пары, уроки).',
  slot: (n: number) => `№ ${n}`,
  ownTime: 'Своё время',
  otherRules: 'Другие повторы',
  addRule: 'Правило',
  newRule: 'Новое правило',
  editRule: 'Правило расписания',
  addRuleCell: 'Добавить правило',
  noGrid: 'Сетки слотов нет — правила со своим временем. Сетку можно завести в настройках периода.',
  noTypes: 'Сначала заведите тип занятости — «Урок», «Смена», «Встреча».',
  noRules: 'Правил пока нет.',
  eventType: 'Тип занятости',
  area: 'Сфера',
  noArea: 'Без сферы',
  newArea: (typeName: string) => `＋ ${typeName}`,
  pattern: 'Как повторяется',
  weekdays: 'Дни недели',
  on: 'Рабочих дней',
  off: 'Выходных',
  anchor: 'Первый рабочий день',
  date: 'Дата',
  rrule: 'Правило RRULE',
  rruleHint: 'Без DTSTART и времени: FREQ=MONTHLY;BYDAY=2TU.',
  time: 'Время',
  byTime: 'Время',
  bySlots: 'Слоты',
  start: 'Начало',
  end: 'Конец',
  overnightHint: 'Конец раньше начала — до следующего дня.',
  slotFrom: 'С',
  slotTo: 'по',
  grid: 'Сетка',
  ruleTitle: 'Название',
  titleHint: 'Пусто — название сферы, без неё — типа занятости.',
  location: 'Где',
  validity: 'Только часть периода…',
  validFrom: 'Действует с',
  validTo: 'по',
  note: 'Заметка к правилу',
  copy: 'Копировать',
  copyToDay: 'На день',
  copyToWeek: 'На неделю цикла',
  copied: 'Скопировано',
  deleteTitle: 'Удалить правило?',
  deleteDescription: 'Будущие вхождения исчезнут из календаря. Прошедшие останутся.',
  deleteLabel: 'Удалить правило',
  save: 'Сохранить',
  saving: 'Сохраняем…',
  required: 'Обязательно',
  timeRequired: 'Укажите время',
  sameTime: 'Конец совпадает с началом',
  slotRequired: 'Выберите слот',
  daysRequired: 'Выберите дни',
  // периоды
  name: 'Название',
  startDate: 'Начало',
  endDate: 'Последний день',
  cycle: 'Цикл недель',
  cycleHint: '1 — без цикла; 2 — бывшие числитель и знаменатель.',
  firstWeek: 'Первая неделя — неделя цикла',
  pauses: 'Паузы',
  pausesHint: 'Сессия, каникулы: правила периода в эти дни не повторяются.',
  addPause: 'Пауза',
  pauseTitle: 'Каникулы, сессия…',
  createPeriod: 'Создать период',
  deletePeriodTitle: (name: string) => `Удалить «${name}»?`,
  deletePeriodDescription: 'Правила, сетки и исключения периода удалятся. Сферы останутся без периода.',
  deletePeriodLabel: 'Удалить период',
  // сетки
  defaultGrid: 'Звонки',
  gridName: 'Название сетки',
  allDays: 'Все дни',
  ownForDay: 'Свои для дня…',
  addSlot: 'Слот',
  removeSlot: 'Убрать слот',
  likeAllDays: 'Как во все дни',
  saveGrid: 'Сохранить сетку',
  gridSaved: 'Сетка сохранена',
  slotStart: (n: number) => `${n}: начало`,
  slotEnd: (n: number) => `${n}: конец`,
  // исключения
  daysOff: 'Исключения',
  daysOffHint: 'Дни без правил периода: праздники, практика. Правила без периода исключения не трогают.',
  noDaysOff: 'Исключений пока нет.',
  dayOffFrom: 'С',
  dayOffTo: 'По (необязательно)',
  dayOffTitle: 'Праздник, практика…',
  allPeriods: 'Во всех периодах',
  add: 'Добавить',
  remove: 'Удалить',
  dates: 'Даты',
}

export const EVENT_TYPES_UI = {
  title: 'Типы занятости',
  description:
    'Жёсткие события: уроки, смены, встречи. Тип задаёт дорогу, напоминание и поля; план в это время ничего не ставит.',
  empty: 'Типов занятости нет — разовые события в календаре просто занимают время.',
  add: 'Тип занятости',
  newTitle: 'Новый тип занятости',
  name: 'Название',
  namePlaceholder: 'Смена',
  plural: 'Во множественном числе',
  pluralHint: 'Заголовок в утренней сводке.',
  icon: 'Иконка',
  color: 'Цвет',
  remind: 'Напоминать за',
  remindOff: 'Не напоминать',
  channels: 'Куда',
  buffer: 'Дорога',
  bufferBefore: 'до',
  bufferAfter: 'после',
  minutes: 'мин',
  more: 'Подробнее',
  less: 'Скрыть',
  merge: 'Склеивать дорогу',
  mergeHint: 'Подряд в день с тем же местом — дорога только до первого и после последнего.',
  budgets: 'Входит в лимиты',
  budgetsHint: 'Время событий этого типа засчитывается в лимит дня.',
  noBudgets: 'Лимитов нет — завести можно в разделе «Лимиты».',
  rest: 'Это отдых',
  restHint: 'Защищённое время: план туда ничего не ставит.',
  prep: 'Нужна подготовка',
  prepHint: 'Экзамен, выступление: подготовка распределяется до события.',
  nowNext: 'Карточка «Сейчас / Дальше»',
  nowNextHint: 'На экране «Сегодня» и отдельной секцией в утренней сводке.',
  locationLabel: 'Подпись места',
  locationLabelHint: 'В текстах перед местом: «ауд.» → «ауд. 1801».',
  fields: 'Поля событий',
  fieldsHint: 'С флагом «в напоминании» видны в сводке и напоминании. Поля не влияют на план.',
  deleteTitle: (name: string) => `Удалить тип «${name}»?`,
  deleteDescription: 'Правила этого типа и их будущие события удалятся. Прошедшие останутся.',
  deleteLabel: 'Удалить тип занятости',
  remindChip: (m: number) => `за ${m} мин`,
  bufferChip: (m: number) => `дорога ${m} мин`,
  save: 'Сохранить',
  saving: 'Сохраняем…',
}

export const EVENT_UI = {
  newTitle: 'Новое событие',
  type: 'Тип занятости',
  noType: 'Без типа',
  title: 'Что',
  titlePlaceholder: 'Врач, встреча, кино…',
  when: 'Когда',
  from: 'Начиная с',
  start: 'Начало',
  end: 'Конец',
  repeat: 'Повтор',
  repeatOn: 'Повторяется в выбранные дни — правило без периода.',
  noRepeat: (day: string | null) =>
    `Не повторяется. Нажмите дни, чтобы повторять${day ? ` (например, ${day})` : ''}.`,
  until: 'До (необязательно)',
  area: 'Сфера',
  where: 'Где',
  color: 'Цвет',
  note: 'Заметка',
  save: 'Сохранить',
  saving: 'Сохраняем…',
  titleRequired: 'Как назвать?',
  dateRequired: 'Укажите дату',
  sameTime: 'Конец совпадает с началом',
  endBeforeStart: 'Конец раньше начала',
  typeForRepeat: 'Для повтора выберите тип занятости',
  recurring: 'Повторяющиеся',
  // карточка
  slot: (n: number) => `№ ${n}`,
  cancelled: 'Отменено',
  done: 'Сделано',
  missed: 'Не сделано',
  pinned: 'Закреплено',
  detached: 'Изменено вручную',
  edit: 'Изменить',
  move: 'Перенести',
  skip: 'Отменить',
  asScheduled: 'Как в расписании',
  series: 'Всё правило',
}

export const NOW_NEXT_UI = {
  now: 'Сейчас',
  next: 'Дальше',
  upcoming: 'Следующее',
  left: (t: string) => `ещё ${t}`,
  inTime: (t: string) => `через ${t}`,
  dayOff: (title: string) => `Сегодня исключение: ${title}`,
  over: 'На сегодня всё закончилось',
  empty: 'Сегодня событий нет',
}

// ---------- сферы и поля (M16) ----------

/** Разделы страницы сферы — порядок задаёт тип сферы. */
export const AREA_SECTION_LABEL: Record<Schemas['AreaSection'], string> = {
  schedule: 'Расписание',
  tasks: 'Задачи',
  notes: 'Заметки',
  materials: 'Материалы',
  prep: 'Подготовка',
  projects: 'Проекты',
}

export const FIELD_TYPE_LABEL: Record<Schemas['FieldType'], string> = {
  text: 'Текст',
  number: 'Число',
  bool: 'Да / нет',
  select: 'Один из списка',
  multiselect: 'Несколько из списка',
  date: 'Дата',
  contact: 'Контакт',
  link: 'Ссылка',
  area_ref: 'Сфера',
}

export const CONTACT_LABEL = {
  name: 'Имя',
  role: 'Роль',
  phone: 'Телефон',
  email: 'Email',
  link: 'Ссылка',
  note: 'Заметка',
} as const

export const FIELDS_UI = {
  yes: 'да',
  no: 'нет',
  none: 'Не выбрано',
  add: 'Добавить',
  remove: 'Убрать',
  linkTitle: 'Название',
  required: 'Обязательное поле',
}

export const AREAS_UI = {
  title: 'Сферы',
  /** Пункт меню и вкладка списка. */
  tab: 'Сферы',
  empty: 'Сфер пока нет. Сфера — всё, по чему хочется открыть занятия, задачи и заметки разом: предмет, ученик, клиент, секция.',
  noTypes: 'Сначала заведите тип сферы — «Предмет», «Ученик», «Клиент».',
  addType: 'Тип сферы',
  archived: 'В архиве',
  area: 'Сфера',
  noArea: 'Без сферы',
  newTitle: (typeName: string) => `Новая сфера: ${typeName.toLowerCase()}`,
  type: 'Тип',
  name: 'Название',
  shortName: 'Коротко',
  color: 'Цвет',
  period: 'Период',
  noPeriod: 'Всегда',
  synonyms: 'Другие названия',
  synonymsHint: 'Через запятую — чтобы узнавать сферу в быстром вводе.',
  notes: 'Заметки',
  archive: 'В архив',
  unarchive: 'Из архива',
  archivedToast: 'Сфера в архиве',
  edit: 'Изменить сферу',
  back: 'Назад',
  notFound: 'Сфера не найдена.',
  deleteTitle: (name: string) => `Удалить «${name}»?`,
  deleteDescription: 'Занятия этой сферы исчезнут из расписания. Задачи и заметки останутся.',
  deleteLabel: 'Удалить сферу',
  deleted: 'Сфера удалена',
  save: 'Сохранить',
  saving: 'Сохраняем…',
  /** Вкладка «Расписание» сферы. */
  rules: 'Правила',
  noRules: 'Правил нет — добавьте во вкладке',
  scheduleLink: '«Расписание»',
  upcoming: 'Ближайшие',
  past: 'Прошедшие',
  cancelled: 'отменено',
  note: 'Конспект',
  slot: (n: number) => `№ ${n}`,
}

export const AREA_TYPES_UI = {
  title: 'Типы сфер',
  description: 'Какие бывают сферы: «Предмет», «Ученик», «Клиент». Тип задаёт поля и разделы страницы сферы.',
  empty: 'Типов сфер нет — задачи и заметки живут без сфер.',
  add: 'Тип сферы',
  newTitle: 'Новый тип сферы',
  name: 'Название',
  namePlaceholder: 'Ученик',
  plural: 'Во множественном числе',
  pluralPlaceholder: 'Ученики',
  icon: 'Иконка',
  color: 'Цвет по умолчанию',
  more: 'Подробнее',
  less: 'Скрыть',
  sections: 'Разделы страницы',
  fields: 'Поля',
  fieldsHint: 'Значения видны на карточке сферы. Поля не влияют на план.',
  addField: 'Поле',
  fieldLabel: 'Название поля',
  fieldType: 'Тип',
  options: 'Варианты',
  optionsHint: 'Через запятую.',
  multiple: 'Несколько значений',
  required: 'Обязательное',
  inReminder: 'Показывать в напоминании',
  moveUp: 'Выше',
  moveDown: 'Ниже',
  removeField: 'Убрать поле',
  removeFieldHint: 'Значения убранного поля не стираются: верните поле — они вернутся.',
  fieldsCount: (n: number) => `полей: ${n}`,
  deleteTitle: (name: string) => `Удалить тип «${name}»?`,
  deleteDescription: 'Тип удаляется, только если у него нет сфер.',
  deleteLabel: 'Удалить тип сферы',
  save: 'Сохранить',
  saving: 'Сохраняем…',
}

// ---------- долгий ящик ----------

export const CONDITION_LABEL: Record<Schemas['BacklogCondition'], string> = {
  weekday_daytime: 'В будни днём',
  needs_laptop: 'Нужен ноутбук',
}

/** «В дни событий типа» (бывший чип «в дни пар»). */
export const BACKLOG_DAYS = {
  label: 'Только в дни',
  any: 'В любой день',
  chip: (plural: string) => `В дни: ${plural.toLowerCase()}`,
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
  morning_digest: { title: 'Утренняя сводка', description: 'События, дела и дедлайны на день.' },
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
  eventMembers: 'Какая занятость входит',
  eventMembersHint: 'Время событий этих типов тоже идёт в лимит.',
  perDay: (hours: number) => `до ${hours} ч в день`,
  deleteTitle: (name: string) => `Удалить лимит «${name}»?`,
  deleteDescription: 'План перестанет ограничивать эти дела по часам.',
  deleteLabel: 'Удалить лимит',
  save: 'Сохранить',
  saving: 'Сохраняем…',
}
