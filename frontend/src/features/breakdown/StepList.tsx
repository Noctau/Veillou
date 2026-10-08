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
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVerticalIcon, LinkIcon, PlusIcon, Trash2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { ActionTypeSelect } from '@/features/catalog/CatalogSelect'
import { cn } from '@/lib/utils'

import { type DraftStep, MAX_STEP, MIN_STEP, moveStep, newKey, removeStep, validStep } from './draft'

function StepRow({
  step,
  index,
  above,
  onChange,
  onRemove,
}: {
  step: DraftStep
  index: number
  above: DraftStep[]
  onChange: (patch: Partial<DraftStep>) => void
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: step.key,
  })
  const number = new Map(above.map((s, i) => [s.key, i + 1]))
  const deps = step.depends_on.map((k) => number.get(k)).filter(Boolean)
  const invalid = !validStep(step)

  return (
    <li
      ref={setNodeRef}
      // Исключение из «без inline style»: dnd-kit двигает элемент через transform
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        'flex gap-1 rounded-lg border bg-card p-2',
        isDragging && 'relative z-10 shadow-lg ring-1 ring-border',
        invalid && 'border-destructive/60',
      )}
    >
      <div className="flex flex-col items-center gap-1 pt-1.5">
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
        <span className="text-xs text-muted-foreground tabular-nums">{index + 1}</span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <Input
          value={step.title}
          aria-label={`Шаг ${index + 1}`}
          placeholder="Что сделать"
          onChange={(e) => onChange({ title: e.target.value })}
        />
        <div className="flex flex-wrap items-center gap-1.5">
          <div className="flex items-center gap-1">
            <Input
              type="number"
              inputMode="numeric"
              min={MIN_STEP}
              max={MAX_STEP}
              step={5}
              value={Number.isFinite(step.estimate_min) ? step.estimate_min : ''}
              aria-label="Оценка, мин"
              className="h-8 w-20"
              onChange={(e) => onChange({ estimate_min: e.target.value === '' ? NaN : Number(e.target.value) })}
            />
            <span className="text-xs text-muted-foreground">мин</span>
          </div>
          <div className="w-44 [&_button]:h-8">
            <ActionTypeSelect
              value={step.action_type_id}
              emptyLabel="Как у задания"
              onChange={(action_type_id) => onChange({ action_type_id })}
            />
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="ghost" size="sm" className="h-8" disabled={above.length === 0}>
                <LinkIcon />
                {deps.length ? `после ${deps.join(', ')}` : 'после…'}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="max-w-72">
              <DropdownMenuLabel>Начать после шагов</DropdownMenuLabel>
              {above.map((s, i) => (
                <DropdownMenuCheckboxItem
                  key={s.key}
                  checked={step.depends_on.includes(s.key)}
                  onSelect={(e) => e.preventDefault()}
                  onCheckedChange={(on) =>
                    onChange({
                      depends_on: on ? [...step.depends_on, s.key] : step.depends_on.filter((k) => k !== s.key),
                    })
                  }
                >
                  <span className="truncate">
                    {i + 1}. {s.title || 'Без названия'}
                  </span>
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="ml-auto size-8 text-muted-foreground"
            aria-label="Удалить шаг"
            onClick={onRemove}
          >
            <Trash2Icon />
          </Button>
        </div>
        {step.note && <p className="text-xs text-muted-foreground">{step.note}</p>}
      </div>
    </li>
  )
}

/** Редактируемый список шагов черновика: правка, удаление, добавление, перетаскивание, зависимости. */
export function StepList({ steps, onChange }: { steps: DraftStep[]; onChange: (steps: DraftStep[]) => void }) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return
    const keys = steps.map((s) => s.key)
    onChange(moveStep(steps, keys.indexOf(String(active.id)), keys.indexOf(String(over.id))))
  }
  const patch = (key: string, p: Partial<DraftStep>) => onChange(steps.map((s) => (s.key === key ? { ...s, ...p } : s)))
  const add = () =>
    onChange([...steps, { key: newKey(), title: '', estimate_min: 30, action_type_id: null, depends_on: [], note: '' }])

  return (
    <div className="flex flex-col gap-2">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={steps.map((s) => s.key)} strategy={verticalListSortingStrategy}>
          <ul className="flex flex-col gap-2">
            {steps.map((s, i) => (
              <StepRow
                key={s.key}
                step={s}
                index={i}
                above={steps.slice(0, i)}
                onChange={(p) => patch(s.key, p)}
                onRemove={() => onChange(removeStep(steps, s.key))}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
      <Button type="button" variant="outline" size="sm" className="self-start" onClick={add}>
        <PlusIcon /> Добавить шаг
      </Button>
    </div>
  )
}
