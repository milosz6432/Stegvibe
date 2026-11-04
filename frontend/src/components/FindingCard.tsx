import { ChevronDown, ChevronRight, Info } from 'lucide-react'
import * as React from 'react'

import type { Finding } from '@/api/types'
import { ConfidenceBadge, KindBadge } from '@/components/badges'
import { CopyButton } from '@/components/common'
import { cn, formatDateTime } from '@/lib/utils'

function Json({ value }: { value: unknown }) {
  return (
    <pre className="mono max-h-56 overflow-auto rounded-md border bg-background p-2 text-[11.5px] leading-4 whitespace-pre-wrap break-all">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

/** A finding with everything needed to reproduce it: plugin@version, exact configuration, evidence hash. */
export function FindingCard({ finding: f, defaultOpen = false }: { finding: Finding; defaultOpen?: boolean }) {
  const [open, setOpen] = React.useState(defaultOpen)
  const hasLocation = f.location && Object.keys(f.location).length > 0
  return (
    <article className="rounded-md border bg-card">
      <button
        type="button"
        className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-accent/40"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronDown className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" /> : <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <ConfidenceBadge confidence={f.confidence} />
            <KindBadge kind={f.kind} />
            <span className={cn('text-[13px] font-medium', f.title.startsWith('INTEGRITY FAILURE') && 'text-destructive')}>{f.title}</span>
          </div>
          <div className="mono mt-0.5 text-[11px] text-muted-foreground">
            {f.plugin_id}@{f.plugin_version} · {formatDateTime(f.created_at)}
          </div>
        </div>
      </button>
      {open ? (
        <div className="space-y-3 border-t px-3 py-3 text-xs">
          {f.description ? <p className="text-[13px]">{f.description}</p> : null}
          {hasLocation ? (
            <div>
              <div className="label-caps mb-1">Location in evidence</div>
              <Json value={f.location} />
            </div>
          ) : null}
          {Object.keys(f.data).length > 0 ? (
            <div>
              <div className="label-caps mb-1">Data</div>
              <Json value={f.data} />
            </div>
          ) : null}
          <div>
            <div className="label-caps mb-1">Reproduce this finding</div>
            <div className="space-y-1 rounded-md border bg-background p-2">
              <div className="mono text-[11.5px]">
                plugin <span className="text-foreground">{f.plugin_id}@{f.plugin_version}</span>
              </div>
              <div className="mono flex items-center gap-1 text-[11.5px]">
                evidence sha256 <span className="truncate text-foreground">{f.evidence_sha256}</span>
                <CopyButton text={f.evidence_sha256} label="Copy evidence SHA-256" />
              </div>
              <div className="mono text-[11.5px]">
                configuration <span className="text-foreground">{JSON.stringify(f.config)}</span>
              </div>
            </div>
          </div>
          {f.limitations ? (
            <div className="flex gap-2 rounded-md border border-warn/30 bg-warn/5 p-2 text-warn">
              <Info className="mt-px size-3.5 shrink-0" />
              <div>
                <div className="label-caps text-warn">Limitations</div>
                <div className="text-[12px] text-foreground/90">{f.limitations}</div>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}
