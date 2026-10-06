import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { CalendarIcon, ClockIcon, GripVerticalIcon, LockIcon, PlusIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { byId, useActionTypes } from '@/features/catalog/useCatalog'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { formatDay, wallDate, wallTime } from '@/lib/time'
import { cn } from '@/lib/utils'

import { FEEL_LABEL, formatMinutes } from './labels'
import { SubtaskDialog } from './SubtaskDialog'
import { useAddSubtask, useReorderSubtasks, useUpdateSubtask } from './useSubtasks'
import type { Feel, Subtask, TaskDetail } from './useTasks'

const FEELS: Feel[] = ['faster', 'ok', 'slower']

function Row({
  subtask,
  titles,
  taskActionTypeId,
  justDone,
  onToggle,
  onFeel,
  onOpen,
}: {
  subtask: Subtask
  titles: Map<string, Subtask>
  taskActionTypeId: string | null
  justDone: boolean
  onToggle: () => void
  onFeel: (feel: Feel) => void
  onOpen: () => void
}) {
  const tz = useTimeZone()
  const { data: actionTypes } = useActionTypes()
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: subtask.id,
  })
  const done = subtask.status === 'done'
  const blocked = !done && subtask.depends_on.some((d) => titles.get(d)?.status !== 'done')
  const block = subtask.events.find((e) => e.status === 'planned')
  const ownType =
    subtask.action_type_id && subtask.action_type_id !== taskActionTypeId
      ? byId(actionTypes).get(subtask.action_type_id)?.name
      : null

  return (
    <li
      ref={setNodeRef}
      // Исключение из «без inline style»: dnd-kit двигает элемент через transform
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn('flex flex-col rounded-lg bg-card', isDragging && 'relative z-10 shadow-lg ring-1 ring-border')}
    >
      <div className="flex items-center gap-2 py-1.5 pr-1">
        <button
          ref={setActivatorNodeRef}
          type="button"
          aria-label="Перетащить"
          className="cursor-grab touch-none p-1 text-muted-foreground active:cursor-grabbing"
          {...attributes}
          {...listeners}
        >
          <GripVerticalIcon className="size-4" />
        </button>
        <Checkbox aria-label={done ? 'Не сделано' : 'Сделано'} className="size-5" checked={done} onCheckedChange={onToggle} />
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
          <span className={cn('block truncate text-sm', done && 'text-muted-foreground line-through')}>{subtask.title}</span>
          <span className="flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <ClockIcon className="size-3" />
              {formatMinutes(subtask.estimate_min)}
            </span>
            {ownType && <span>{ownType}</span>}
            {block && (
              <span className="flex items-center gap-1 text-foreground">
                <CalendarIcon className="size-3" />
                {formatDay(wallDate(block.start, tz))}, {wallTime(block.start, tz)}
              </span>
            )}
            {blocked && (
              <span className="flex items-center gap-1">
                <LockIcon className="size-3" />
                после «{subtask.depends_on.map((d) => titles.get(d)?.title).filter(Boolean).join('», «')}»
              </span>
            )}
          </span>
        </button>
      </div>
      {justDone && done && !subtask.actual_feel && (
        <div className="flex items-center gap-1 pb-2 pl-14 text-xs text-muted-foreground">
          <span className="mr-1">Как по времени?</span>
          {FEELS.map((f) => (
            <Button key={f} type="button" variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={() => onFeel(f)}>
              {FEEL_LABEL[f]}
            </Button>
          ))}
        </div>
      )}
    </li>
  )
}

function AddRow({ taskId }: { taskId: string }) {
  const add = useAddSubtask(taskId)
  const [title, setTitle] = useState('')
  const [estimate, setEstimate] = useState('30')
  const submit = () => {
    const minutes = Number(estimate)
    if (!title.trim() || !(minutes >= 5 && minutes <= 600)) return
    add.mutate({ title: title.trim(), estimate_min: minutes, depends_on: [], note: '' })
    setTitle('')
  }
  return (
    <form
      className="flex items-center gap-2 pl-7"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Новый шаг" aria-label="Новый шаг" />
      <Input
        type="number"
        inputMode="numeric"
        min={5}
        max={600}
        step={5}
        value={estimate}
        onChange={(e) => setEstimate(e.target.value)}
        aria-label="Оценка, мин"
        className="w-20"
      />
      <Button type="submit" size="icon" variant="outline" aria-label="Добавить шаг" disabled={!title.trim() || add.isPending}>
        <PlusIcon />
      </Button>
    </form>
  )
}

/** Подзадачи: отметки, перетаскивание за ручку, зависимости, постановка в календарь. */
export function SubtaskList({ task }: { task: TaskDetail }) {
  const reorder = useReorderSubtasks(task.id)
  const update = useUpdateSubtask(task.id)
  const [openedId, setOpenedId] = useState<string | null>(null)
  const [justDone, setJustDone] = useState<Set<string>>(new Set())
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const subtasks = task.subtasks
  const titles = new Map(subtasks.map((s) => [s.id, s]))
  const opened = subtasks.find((s) => s.id === openedId) ?? null

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return
    const ids = subtasks.map((s) => s.id)
    reorder.mutate(arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id))))
  }

  const toggle = (s: Subtask) => {
    const status = s.status === 'done' ? 'todo' : 'done'
    update.mutate({ id: s.id, body: { status } })
    if (status === 'done') setJustDone((old) => new Set(old).add(s.id))
  }

  return (
    <div className="flex flex-col gap-2">
      {subtasks.length === 0 && (
        <p className="text-sm text-muted-foreground">Разбейте задание на шаги по 15–120 минут — так их проще ставить в план.</p>
      )}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={subtasks.map((s) => s.id)} strategy={verticalListSortingStrategy}>
          <ul className="flex flex-col">
            {subtasks.map((s) => (
              <Row
                key={s.id}
                subtask={s}
                titles={titles}
                taskActionTypeId={task.action_type_id}
                justDone={justDone.has(s.id)}
                onToggle={() => toggle(s)}
                onFeel={(feel) => update.mutate({ id: s.id, body: { actual_feel: feel } })}
                onOpen={() => setOpenedId(s.id)}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
      <AddRow taskId={task.id} />
      <SubtaskDialog
        taskId={task.id}
        subtask={opened}
        siblings={subtasks}
        onOpenChange={(open) => !open && setOpenedId(null)}
      />
    </div>
  )
}
