import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <div className="py-16 text-center">
      <p className="mb-4 text-muted-foreground">Такой страницы нет.</p>
      <Link to="/" className="text-primary underline underline-offset-4">
        На главную
      </Link>
    </div>
  )
}
