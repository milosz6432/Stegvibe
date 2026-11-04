import * as React from 'react'

import { cn } from '@/lib/utils'

const field =
  'w-full rounded-md border border-input bg-background px-2.5 text-[13px] text-foreground placeholder:text-muted-foreground/70 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:border-ring'

export function Input({ className, ...props }: React.ComponentProps<'input'>) {
  return <input className={cn(field, 'h-8', className)} {...props} />
}

export function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return <textarea className={cn(field, 'min-h-16 py-1.5', className)} {...props} />
}

export function Select({ className, children, ...props }: React.ComponentProps<'select'>) {
  return (
    <select className={cn(field, 'h-8 pr-6', className)} {...props}>
      {children}
    </select>
  )
}

export function Field({ label, hint, children, className }: { label: string; hint?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn('block space-y-1', className)}>
      <span className="label-caps">{label}</span>
      {children}
      {hint ? <span className="block text-[11px] text-muted-foreground">{hint}</span> : null}
    </label>
  )
}
