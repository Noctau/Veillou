/**
 * Общее для приложения и service worker: имена кэшей и то, что пришло через «Поделиться».
 * Без DOM-зависимостей — файл компилируется и в SW (lib WebWorker).
 */
import { createStore, del, entries, get, set } from 'idb-keyval'

/** GET /api: сеть, без сети — последний ответ. */
export const API_CACHE = 'veillou-api'
/** Файлы по подписанным ссылкам (страницы фото-конспектов) — для офлайна. */
export const FILES_CACHE = 'veillou-files'

export const SHARE_TARGET_PATH = '/share-target'
export const SHARE_PARAM = 'share'
const SHARE_TTL_MS = 24 * 60 * 60_000

/**
 * Ссылка на файл подписана и меняется раз в час, сам файл — нет: ключ кэша без exp/sig.
 * v= — версия содержимого (sha): после поворота страницы ключ новый.
 */
export function fileCacheKey(url: string | URL): string {
  const u = new URL(url)
  const key = new URL(u.origin + u.pathname)
  for (const name of ['v', 'download']) {
    const value = u.searchParams.get(name)
    if (value) key.searchParams.set(name, value)
  }
  return key.href
}

// ---------- «Поделиться» ----------

export type SharedItem = {
  id: string
  createdAt: number
  title: string
  text: string
  url: string
  files: File[]
}

const shareStore = createStore('veillou-share', 'items')

export async function saveShare(item: SharedItem): Promise<void> {
  await set(item.id, item, shareStore)
}

export function loadShare(id: string): Promise<SharedItem | undefined> {
  return get<SharedItem>(id, shareStore)
}

export function deleteShare(id: string): Promise<void> {
  return del(id, shareStore)
}

/** Брошенные «Поделиться» (закрыла экран, не сохранив) живут сутки. */
export async function pruneShares(now = Date.now()): Promise<void> {
  const all = await entries<string, SharedItem>(shareStore)
  await Promise.all(
    all.filter(([, item]) => now - item.createdAt > SHARE_TTL_MS).map(([id]) => del(id, shareStore)),
  )
}

/** Текст для строки быстрого ввода: заголовок, текст и ссылка без повторов. */
export function shareText(item: Pick<SharedItem, 'title' | 'text' | 'url'>): string {
  const parts: string[] = []
  for (const raw of [item.title, item.text, item.url]) {
    const part = raw.trim()
    if (part && !parts.some((p) => p.includes(part))) parts.push(part)
  }
  return parts.join(' ')
}
