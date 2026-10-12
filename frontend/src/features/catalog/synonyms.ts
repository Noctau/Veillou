/** «реферат, Эссе ,» → ["реферат", "Эссе"] */
export function parseSynonyms(text: string): string[] {
  return text
    .split(',')
    .map((w) => w.trim())
    .filter(Boolean)
}
