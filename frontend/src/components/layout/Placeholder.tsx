import { Card, CardContent } from '@/components/ui/card'

export function Placeholder({ text }: { text: string }) {
  return (
    <Card>
      <CardContent className="py-8 text-center text-sm text-muted-foreground">{text}</CardContent>
    </Card>
  )
}
