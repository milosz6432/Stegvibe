import * as React from 'react'

import type { AuditEntry } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/table'
import { formatDateTime, shortId } from '@/lib/utils'

function summarize(details: Record<string, unknown>): string {
  const s = JSON.stringify(details)
  return s === '{}' ? '' : s.length > 120 ? `${s.slice(0, 117)}…` : s
}

export function AuditList({ entries, showIds = false }: { entries: AuditEntry[]; showIds?: boolean }) {
  const [open, setOpen] = React.useState<number | null>(null)
  return (
    <Table>
      <THead>
        <tr>
          <TH className="w-14">#</TH>
          <TH className="w-44">Time</TH>
          <TH className="w-24">Actor</TH>
          <TH className="w-44">Action</TH>
          <TH>Details</TH>
        </tr>
      </THead>
      <TBody>
        {entries.map((e) => (
          <React.Fragment key={e.seq}>
            <TR className="cursor-pointer" onClick={() => setOpen(open === e.seq ? null : e.seq)}>
              <TD className="mono text-muted-foreground">{e.seq}</TD>
              <TD className="mono text-[12px] whitespace-nowrap">{formatDateTime(e.ts)}</TD>
              <TD>
                <Badge variant={e.actor === 'system' ? 'outline' : 'default'}>{e.actor}</Badge>
              </TD>
              <TD className="mono text-[12px]">{e.action}</TD>
              <TD className="mono max-w-0 truncate text-[11.5px] text-muted-foreground">
                {showIds && e.evidence_id ? `ev:${shortId(e.evidence_id)} ` : ''}
                {summarize(e.details)}
              </TD>
            </TR>
            {open === e.seq ? (
              <tr className="border-b bg-background">
                <td colSpan={5} className="space-y-2 px-3 py-2">
                  <pre className="mono max-h-52 overflow-auto text-[11.5px] whitespace-pre-wrap break-all">{JSON.stringify(e.details, null, 2)}</pre>
                  <div className="mono text-[11px] text-muted-foreground">
                    prev {e.prev_hash.slice(0, 16)}… → entry {e.entry_hash.slice(0, 16)}…
                  </div>
                </td>
              </tr>
            ) : null}
          </React.Fragment>
        ))}
      </TBody>
    </Table>
  )
}
