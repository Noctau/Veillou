import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { setSpellcheckEnabled, useSpellcheck } from '@/lib/spellcheck'

const HINTS: { where: string; how: string }[] = [
  {
    where: 'Chrome, Edge, Яндекс Браузер',
    how: 'Настройки → Языки → «Проверка правописания»: включите и добавьте русский и английский.',
  },
  { where: 'Safari, iPhone и iPad', how: 'Языки берутся из системы: добавьте английский в «Язык и регион» и раскладку клавиатуры.' },
  {
    where: 'Firefox',
    how: 'Правый клик в поле → «Языки» → «Добавить словари…»: поставьте русский и английский.',
  },
  { where: 'Android', how: 'Проверяет клавиатура: в Gboard включите «Проверка правописания» и оба языка.' },
]

/** Проверка правописания полей ввода: вкл/выкл на этом устройстве и подсказки по браузерам. */
export function SpellcheckSection() {
  const on = useSpellcheck()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Проверка правописания</CardTitle>
        <CardDescription>
          Ошибки подчёркиваются прямо в полях — в названиях, описаниях, заметках. Исправление — правым кликом или
          тапом по слову. Проверяет сам браузер, текст никуда не уходит.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pt-4">
        <Field orientation="horizontal">
          <Switch id="spellcheck" checked={on} onCheckedChange={setSpellcheckEnabled} />
          <FieldLabel htmlFor="spellcheck">Проверять правописание на этом устройстве</FieldLabel>
        </Field>
        <Field>
          <FieldLabel htmlFor="spellcheck-try">Попробовать</FieldLabel>
          <Textarea
            id="spellcheck-try"
            rows={2}
            defaultValue="Превет, это проверка. Thiss is a test."
            disabled={!on}
          />
          <FieldDescription>Ошибки не подчёркнуты? Включите словари русского и английского:</FieldDescription>
        </Field>
        <dl className="grid gap-2 text-sm">
          {HINTS.map((h) => (
            <div key={h.where}>
              <dt className="font-medium">{h.where}</dt>
              <dd className="text-muted-foreground">{h.how}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
