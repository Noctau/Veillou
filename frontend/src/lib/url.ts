/** Ссылка из поля ввода: без схемы допишем https://. Не http(s) или мусор — null. */
export function normalizeUrl(raw: string): string | null {
  const value = raw.trim()
  if (!value) return null
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : `https://${value}`
  try {
    const url = new URL(withScheme)
    return /^https?:$/.test(url.protocol) && url.hostname.includes('.') ? url.href : null
  } catch {
    return null
  }
}
