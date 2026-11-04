import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <div className="p-10 text-center">
      <div className="mono text-4xl text-muted-foreground">404</div>
      <p className="mt-2 text-sm">There is nothing at this address.</p>
      <Link to="/" className="mt-3 inline-block text-xs text-primary hover:underline">
        Back to the dashboard
      </Link>
    </div>
  )
}
