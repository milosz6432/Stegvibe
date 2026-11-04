import { AlertTriangle, Check, Copy, Loader2 } from 'lucide-react'
import * as React from 'react'

import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = React.useState(false)
  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-6"
      aria-label={`${label}`}
      title={label}
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setDone(true)
          setTimeout(() => setDone(false), 1200)
        })
      }}
    >
      {done ? <Check className="text-ok" /> : <Copy />}
    </Button>
  )
}

export function ErrorNote({ error, className }: { error: unknown; className?: string }) {
  if (!error) return null
  const err = error as Partial<ApiError> & Error
  const details = Array.isArray(err.details) ? (err.details as { loc?: unknown[]; msg?: string }[]) : null
  return (
    <div role="alert" className={cn('flex gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2.5 text-xs text-destructive', className)}>
      <AlertTriangle className="mt-px size-3.5 shrink-0" />
      <div className="min-w-0">
        <div>{err.message ?? 'Something went wrong.'}</div>
        {details?.map((d, i) => (
          <div key={i} className="mono mt-0.5 text-[11px] opacity-80">
            {(d.loc ?? []).join('.')}: {d.msg}
          </div>
        ))}
      </div>
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-4 text-xs text-muted-foreground">
      <Loader2 className="size-3.5 animate-spin" /> {label}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="p-6 text-center">
      <div className="text-sm text-foreground">{title}</div>
      {children ? <div className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">{children}</div> : null}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 border-b px-5 py-3">
      <div className="min-w-0">
        <h1 className="truncate text-base font-semibold tracking-tight">{title}</h1>
        {subtitle ? <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  )
}

/** Monospace value with a copy button; used for hashes and ids. */
export function HashRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 border-b py-1 last:border-0">
      <span className="label-caps w-14 shrink-0">{label}</span>
      <code className="min-w-0 flex-1 truncate text-[12px]" title={value}>
        {value}
      </code>
      <CopyButton text={value} label={`Copy ${label}`} />
    </div>
  )
}
