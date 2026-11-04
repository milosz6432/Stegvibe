import { Download, Square } from 'lucide-react'

import { artifactUrl } from '@/api/client'
import { useCancelJob, usePlugins } from '@/api/hooks'
import type { Job } from '@/api/types'
import { StatusBadge } from '@/components/badges'
import { ErrorNote } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/table'
import { formatDateTime, formatDuration } from '@/lib/utils'

export function JobsTable({ jobs, onShowFindings }: { jobs: Job[]; onShowFindings?: (job: Job) => void }) {
  const cancel = useCancelJob()
  const plugins = usePlugins()
  const nameOf = (id: string) => plugins.data?.find((p) => p.id === id)?.name ?? id
  return (
    <>
      <Table>
        <THead>
          <tr>
            <TH>Analysis</TH>
            <TH className="w-24">Status</TH>
            <TH className="w-48">Progress</TH>
            <TH className="w-32">Started</TH>
            <TH className="w-20">Duration</TH>
            <TH className="w-28" />
          </tr>
        </THead>
        <TBody>
          {jobs.map((j) => {
            const active = j.status === 'queued' || j.status === 'running'
            return (
              <TR key={j.id}>
                <TD>
                  <div className="font-medium">{nameOf(j.plugin_id)}</div>
                  <div className="mono text-[11px] text-muted-foreground">
                    {j.plugin_id}@{j.plugin_version}
                  </div>
                  {j.status === 'failed' || j.status === 'cancelled' ? (
                    <div className="mt-1 text-[11.5px] text-destructive/90" title={j.result?.diagnostics?.traceback}>
                      {j.error_code ? <span className="mono">[{j.error_code}] </span> : null}
                      {j.error_message}
                    </div>
                  ) : null}
                  {j.status === 'succeeded' && j.result?.warnings?.map((w, i) => (
                    <div key={i} className="mt-1 text-[11.5px] text-warn">
                      ⚠ {w}
                    </div>
                  ))}
                  {j.result?.artifacts?.map((a) => (
                    <a key={a.name} className="mono mt-1 flex items-center gap-1 text-[11.5px] text-primary hover:underline" href={artifactUrl(j.id, a.name)}>
                      <Download className="size-3" /> {a.name}
                    </a>
                  ))}
                </TD>
                <TD>
                  <StatusBadge status={j.status} />
                </TD>
                <TD>
                  {active ? (
                    <div className="space-y-1">
                      <Progress value={j.status === 'queued' ? 0 : j.progress} />
                      <div className="truncate text-[11px] text-muted-foreground">{j.status === 'queued' ? 'waiting for a worker' : j.progress_message || `${Math.round(j.progress * 100)}%`}</div>
                    </div>
                  ) : j.status === 'succeeded' ? (
                    <button type="button" className="text-xs text-primary hover:underline" onClick={() => onShowFindings?.(j)}>
                      {j.result?.finding_count ?? 0} finding{j.result?.finding_count === 1 ? '' : 's'}
                    </button>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TD>
                <TD className="mono text-[11.5px] whitespace-nowrap">{formatDateTime(j.started_at ?? j.created_at)}</TD>
                <TD className="mono text-[11.5px]">{formatDuration(j.started_at, j.finished_at)}</TD>
                <TD className="text-right">
                  {active ? (
                    <Button variant="outline" size="sm" disabled={cancel.isPending} onClick={() => cancel.mutate(j.id)}>
                      <Square /> Cancel
                    </Button>
                  ) : null}
                </TD>
              </TR>
            )
          })}
        </TBody>
      </Table>
      <ErrorNote error={cancel.error} className="m-3" />
    </>
  )
}
