/**
 * Палитра предметов и событий. В БД хранится hex, классы Tailwind — литералами,
 * чтобы их увидел сборщик (без inline style).
 */
export const PALETTE = [
  { hex: '#3b82f6', name: 'Синий', bg: 'bg-blue-500', border: 'border-blue-500', soft: 'bg-blue-500/15' },
  { hex: '#06b6d4', name: 'Бирюзовый', bg: 'bg-cyan-500', border: 'border-cyan-500', soft: 'bg-cyan-500/15' },
  { hex: '#10b981', name: 'Зелёный', bg: 'bg-emerald-500', border: 'border-emerald-500', soft: 'bg-emerald-500/15' },
  { hex: '#84cc16', name: 'Салатовый', bg: 'bg-lime-500', border: 'border-lime-500', soft: 'bg-lime-500/15' },
  { hex: '#f59e0b', name: 'Янтарный', bg: 'bg-amber-500', border: 'border-amber-500', soft: 'bg-amber-500/15' },
  { hex: '#f97316', name: 'Оранжевый', bg: 'bg-orange-500', border: 'border-orange-500', soft: 'bg-orange-500/15' },
  { hex: '#ef4444', name: 'Красный', bg: 'bg-red-500', border: 'border-red-500', soft: 'bg-red-500/15' },
  { hex: '#ec4899', name: 'Розовый', bg: 'bg-pink-500', border: 'border-pink-500', soft: 'bg-pink-500/15' },
  { hex: '#8b5cf6', name: 'Фиолетовый', bg: 'bg-violet-500', border: 'border-violet-500', soft: 'bg-violet-500/15' },
  { hex: '#64748b', name: 'Серый', bg: 'bg-slate-500', border: 'border-slate-500', soft: 'bg-slate-500/15' },
] as const

export type PaletteColor = (typeof PALETTE)[number]

const FALLBACK = PALETTE[PALETTE.length - 1]

export function paletteColor(hex: string | null | undefined): PaletteColor {
  return PALETTE.find((c) => c.hex === hex?.toLowerCase()) ?? FALLBACK
}

/** Цвета слоёв календаря для событий без своего цвета. */
export const KIND_COLORS: Record<string, string> = {
  class: '#3b82f6',
  personal: '#8b5cf6',
  rest: '#10b981',
  subtask: '#f59e0b',
  backlog: '#64748b',
  exam_prep: '#ef4444',
}
