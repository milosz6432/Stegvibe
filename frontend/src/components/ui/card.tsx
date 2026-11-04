import * as React from 'react'

import { cn } from '@/lib/utils'

/** A flat, hairline-bordered panel. Panels are the main structural unit of the workstation UI. */
export function Panel({ className, ...props }: React.ComponentProps<'section'>) {
  return <section className={cn('rounded-md border bg-card text-card-foreground', className)} {...props} />
}

export function PanelHeader({ className, title, actions, ...props }: Omit<React.ComponentProps<'header'>, 'title'> & { title: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <header className={cn('flex min-h-9 items-center justify-between gap-2 border-b px-3 py-1.5', className)} {...props}>
      <h2 className="label-caps">{title}</h2>
      {actions ? <div className="flex items-center gap-1.5">{actions}</div> : null}
    </header>
  )
}

export function PanelBody({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('p-3', className)} {...props} />
}
