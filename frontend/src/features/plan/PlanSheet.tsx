import { AlertTriangleIcon, ArrowRightIcon, ChevronDownIcon, ChevronUpIcon, MinusIcon, PlusIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { cn } from '@/lib/utils'

import { AtRiskDialog } from './AtRiskDialog'
import { REASON_LABEL, RISK_LABEL, slotText, summarize } from './labels'
import { type PlanChange, type PlanRisk, useApplyPlan, useDismissPlan, usePlanState } from './usePlan'

const OP_ICON = { move: ArrowRightIcon, add: PlusIcon, remove: MinusIcon, miss: XIcon } as const

function ChangeRow({ change, tz }: { change: PlanChange; tz: string }) {
  const Icon = OP_ICON[change.op]
  return (
    <li className="flex items-start gap-2 py-1 text-sm">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="truncate">{change.title}</div>
        <div className="text-xs text-muted-foreground">
          {change.op === 'move' && change.before && change.after && (
            <>
              {slotText(change.before, tz)} → <span className="text-foreground">{slotText(change.after, tz)}</span>
            </>
          )}
          {change.op === 'add' && change.after && slotText(change.after, tz)}
          {change.op === 'remove' && change.before && `убрать: ${slotText(change.before, tz)}`}
          {change.op === 'miss' && change.before && `не сделано: ${slotText(change.before, tz)}`}
        </div>
      </div>
    </li>
  )
}

/** Угрозы по заданиям: одно задание — одна строка с кнопкой «Варианты». */
function RiskList({ risks, onOptions }: { risks: PlanRisk[]; onOptions: (risk: PlanRisk) => void }) {
  const byTask = new Map<string, PlanRisk[]>()
  for (const r of risks) byTask.set(r.task_id, [...(byTask.get(r.task_id) ?? []), r])
  return (
    <ul className="flex flex-col gap-1">
      {[...byTask.values()].map((items) => (
        <li key={items[0].task_id} className="flex items-center gap-2 text-sm">
          <AlertTriangleIcon className="size-4 shrink-0 text-destructive" />
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">{items[0].task_title}</div>
            <div className="text-xs text-muted-foreground">
              {[...new Set(items.map((r) => RISK_LABEL[r.reason]))].join('; ')}
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => onOptions(items[0])}>
            Варианты
          </Button>
        </li>
      ))}
    </ul>
  )
}

/**
 * Шторка превью перепланирования: «3 блока перенесены, 1 задание под угрозой» +
 * «Применить / Отменить». Ничего в плане не меняется без «Применить».
 */
export function PlanSheet() {
  const tz = useTimeZone()
  const { data } = usePlanState()
  const apply = useApplyPlan()
  const dismiss = useDismissPlan()
  const [expanded, setExpanded] = useState(false)
  const [risk, setRisk] = useState<PlanRisk | null>(null)
  const proposal = data?.proposal

  if (!proposal) return <AtRiskDialog risk={risk} onOpenChange={(open) => !open && setRisk(null)} />

  const hasChanges = proposal.changes.length > 0
  const busy = apply.isPending || dismiss.isPending
  const reason = proposal.reasons.includes('missed') ? 'missed' : proposal.reasons[0]

  return (
    <>
      {/* Место под шторкой: низ страницы можно докрутить до конца */}
      <div aria-hidden className="h-36" />
      <div className="fixed inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-30 px-3 lg:bottom-4 lg:left-60">
        <section
          aria-label="Изменения плана"
          className="mx-auto flex max-w-3xl flex-col gap-2 rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg"
        >
          <button
            type="button"
            className="flex items-start gap-2 text-left"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            <div className="min-w-0 flex-1">
              {reason && <div className="text-xs text-muted-foreground">{REASON_LABEL[reason]}</div>}
              <div className="text-sm font-medium">{summarize(proposal)}</div>
            </div>
            {expanded ? <ChevronDownIcon className="size-5 shrink-0" /> : <ChevronUpIcon className="size-5 shrink-0" />}
          </button>

          {expanded && (
            <div className="flex max-h-[45dvh] flex-col gap-3 overflow-y-auto">
              {proposal.at_risk.length > 0 && <RiskList risks={proposal.at_risk} onOptions={setRisk} />}
              {hasChanges && (
                <ul className="flex flex-col">
                  {proposal.changes.map((c, i) => (
                    <ChangeRow key={`${c.event_id ?? c.source_id}-${i}`} change={c} tz={tz} />
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className={cn('flex flex-wrap justify-end gap-2', !expanded && proposal.at_risk.length > 0 && 'justify-between')}>
            {!expanded && proposal.at_risk.length > 0 && (
              <Button size="sm" variant="ghost" onClick={() => setRisk(proposal.at_risk[0])}>
                <AlertTriangleIcon /> Варианты
              </Button>
            )}
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => dismiss.mutate(proposal.id)}>
                {hasChanges ? 'Отменить' : 'Скрыть'}
              </Button>
              {hasChanges && (
                <Button size="sm" disabled={busy} onClick={() => apply.mutate(proposal.id)}>
                  Применить
                </Button>
              )}
            </div>
          </div>
        </section>
      </div>
      <AtRiskDialog risk={risk} onOpenChange={(open) => !open && setRisk(null)} />
    </>
  )
}
