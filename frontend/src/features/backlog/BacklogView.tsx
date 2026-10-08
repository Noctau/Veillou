import { CalendarCheckIcon, CalendarIcon, ClockIcon, SendIcon } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CategoryIcon } from '@/features/catalog/CategoryIcon'
import { byId, type Category, useCategories } from '@/features/catalog/useCatalog'
import { errorMessage } from '@/lib/errors'
import { formatDay } from '@/lib/time'
import { cn } from '@/lib/utils'

import { BacklogItemDialog } from './BacklogItemDialog'
import { ageLabel, CONDITION_LABEL, estimateLabel } from './labels'
import { type BacklogItem, type BacklogStatus, useBacklog, useCreateBacklog, useUpdateBacklog } from './useBacklog'

function QuickInput() {
  const create = useCreateBacklog()
  const [text, setText] = useState('')
  const submit = () => {
    const title = text.trim()
    if (!title) return
    create.mutate({ title, note: '' })
    setText('')
  }
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Записаться к стоматологу…"
        aria-label="Новое дело"
        enterKeyHint="send"
      />
      <Button type="submit" size="icon" aria-label="Добавить" disabled={!text.trim()}>
        <SendIcon />
      </Button>
    </form>
  )
}

function Row({
  item,
  category,
  onOpen,
}: {
  item: BacklogItem
  category?: Category
  onOpen: (item: BacklogItem) => void
}) {
  const update = useUpdateBacklog()
  const pending = item.id.startsWith('tmp-')
  const estimate = estimateLabel(item.estimate_min)
  return (
    <li className={cn('flex items-center gap-3 rounded-lg px-2 py-2', pending && 'opacity-60')}>
      {item.status === 'active' && (
        <Checkbox
          aria-label="Сделано"
          className="size-5"
          disabled={pending}
          checked={false}
          onCheckedChange={() => update.mutate({ id: item.id, body: { status: 'done' } })}
        />
      )}
      <button type="button" onClick={() => onOpen(item)} className="min-w-0 flex-1 text-left">
        <span className={cn('block truncate text-sm font-medium', item.status === 'done' && 'line-through')}>
          {item.title}
        </span>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {category && (
            <span className="flex items-center gap-1">
              <CategoryIcon name={category.icon} className="size-3" />
              {category.name}
            </span>
          )}
          {estimate && (
            <span className="flex items-center gap-1">
              <ClockIcon className="size-3" />
              {estimate}
            </span>
          )}
          {item.planned_week && item.status === 'active' && (
            <span className="flex items-center gap-1 text-primary">
              <CalendarCheckIcon className="size-3" />
              на неделе
            </span>
          )}
          {item.desired_by && (
            <span className="flex items-center gap-1 text-foreground">
              <CalendarIcon className="size-3" />
              до {formatDay(item.desired_by, { weekday: undefined })}
            </span>
          )}
          {item.conditions.map((c) => (
            <Badge key={c} variant="secondary" className="px-1.5 py-0 text-[10px] font-normal">
              {CONDITION_LABEL[c]}
            </Badge>
          ))}
        </span>
      </button>
      <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{ageLabel(item.created_at)}</span>
    </li>
  )
}

function List({ status, empty, onOpen }: { status: BacklogStatus; empty: string; onOpen: (i: BacklogItem) => void }) {
  const { data: items, isPending, isError, error } = useBacklog(status)
  const { data: categories } = useCategories()
  const cats = byId(categories)
  if (isPending) return <Skeleton className="h-32" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>
  if (!items.length) return <p className="py-8 text-center text-sm text-muted-foreground">{empty}</p>
  return (
    <ul className="flex flex-col">
      {items.map((i) => (
        <Row key={i.id} item={i} category={i.category_id ? cats.get(i.category_id) : undefined} onOpen={onOpen} />
      ))}
    </ul>
  )
}

export function BacklogView() {
  const [opened, setOpened] = useState<BacklogItem | null>(null)
  return (
    <div className="flex flex-col gap-4">
      <QuickInput />
      <Tabs defaultValue="active">
        <TabsList className="mb-2">
          <TabsTrigger value="active">Дела</TabsTrigger>
          <TabsTrigger value="done">Сделано</TabsTrigger>
          <TabsTrigger value="archived">Неактуально</TabsTrigger>
        </TabsList>
        <TabsContent value="active">
          <List status="active" empty="Ящик пуст. Сюда — всё, что «когда-нибудь надо»." onOpen={setOpened} />
        </TabsContent>
        <TabsContent value="done">
          <List status="done" empty="Пока ничего не сделано." onOpen={setOpened} />
        </TabsContent>
        <TabsContent value="archived">
          <List status="archived" empty="Архив пуст." onOpen={setOpened} />
        </TabsContent>
      </Tabs>
      <BacklogItemDialog item={opened} onOpenChange={(open) => !open && setOpened(null)} />
    </div>
  )
}
