import { ShieldCheck, ShieldX } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAudit, useDependencies, useStats, useVerifyAudit } from '@/api/hooks'
import { AuditList } from '@/components/AuditList'
import { ErrorNote, Loading, PageHeader } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Panel, PanelBody, PanelHeader } from '@/components/ui/card'
import { cn, formatBytes } from '@/lib/utils'

const ROADMAP = [
  { n: 1, title: 'Foundation, evidence management, audit, jobs', done: true },
  { n: 2, title: 'Format identification & metadata' },
  { n: 3, title: 'Image Lab' },
  { n: 4, title: 'Audio Lab' },
  { n: 5, title: 'Video Lab' },
  { n: 6, title: 'Analyze Everything & CTF Flag Hunter' },
  { n: 7, title: 'Payload extraction & workspace' },
  { n: 8, title: 'Reports, performance, security hardening' },
]

function Tile({ label, value, sub, to }: { label: string; value: React.ReactNode; sub?: React.ReactNode; to?: string }) {
  const body = (
    <div className="rounded-md border bg-card px-3.5 py-3 transition-colors hover:border-primary/40">
      <div className="label-caps">{label}</div>
      <div className="mono mt-1 text-2xl font-semibold leading-none">{value}</div>
      {sub ? <div className="mt-1.5 text-[11px] text-muted-foreground">{sub}</div> : null}
    </div>
  )
  return to ? <Link to={to}>{body}</Link> : body
}

export function Dashboard() {
  const stats = useStats()
  const audit = useAudit({ limit: 10 })
  const deps = useDependencies()
  const verify = useVerifyAudit()
  const jobs = stats.data?.jobs_by_status ?? {}
  const active = (jobs.running ?? 0) + (jobs.queued ?? 0)

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Local workbench overview. Nothing on this screen leaves your machine." />
      <div className="space-y-4 p-5">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Tile label="Investigations" value={stats.data?.cases ?? '—'} sub={`${stats.data?.archived_cases ?? 0} archived`} to="/investigations" />
          <Tile label="Evidence items" value={stats.data?.evidence ?? '—'} sub={formatBytes(stats.data?.evidence_bytes)} to="/investigations" />
          <Tile label="Findings" value={stats.data?.findings ?? '—'} sub="observations, not verdicts" to="/findings" />
          <Tile label="Jobs" value={active > 0 ? `${active} active` : 'idle'} sub={`${jobs.succeeded ?? 0} ok · ${jobs.failed ?? 0} failed · ${jobs.cancelled ?? 0} cancelled`} />
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <Panel>
            <PanelHeader title="Recent activity (audit log)" />
            {audit.isPending ? <Loading /> : <AuditList entries={audit.data ?? []} showIds />}
            {audit.data?.length === 0 ? <p className="p-4 text-xs text-muted-foreground">Nothing recorded yet.</p> : null}
          </Panel>

          <div className="space-y-4">
            <Panel>
              <PanelHeader title="Audit chain" />
              <PanelBody className="space-y-2 text-xs">
                <p className="text-muted-foreground">
                  Each audit entry is hash-linked to the previous one. Verification detects edited, removed or re-ordered entries; it is tamper-evident, not tamper-proof.
                </p>
                <Button variant="secondary" size="sm" disabled={verify.isPending} onClick={() => verify.mutate()}>
                  Verify chain
                </Button>
                {verify.data ? (
                  <div className={cn('flex items-start gap-2 rounded-md border p-2', verify.data.valid ? 'border-ok/30 text-ok' : 'border-destructive/40 text-destructive')}>
                    {verify.data.valid ? <ShieldCheck className="mt-px size-4 shrink-0" /> : <ShieldX className="mt-px size-4 shrink-0" />}
                    <div className="min-w-0">
                      <div>{verify.data.valid ? `${verify.data.entries_checked} entries verified` : `Chain broken at entry #${verify.data.first_invalid_seq}`}</div>
                      {!verify.data.valid ? <div className="text-foreground/80">{verify.data.reason}</div> : null}
                      <div className="mono mt-0.5 truncate text-[10.5px] text-muted-foreground" title={verify.data.head_hash}>
                        head {verify.data.head_hash.slice(0, 24)}…
                      </div>
                    </div>
                  </div>
                ) : null}
                <ErrorNote error={verify.error} />
              </PanelBody>
            </Panel>

            <Panel>
              <PanelHeader title="Dependencies" actions={<Link to="/settings" className="text-[11px] text-primary hover:underline">details</Link>} />
              <PanelBody className="space-y-1.5 text-xs">
                {deps.data ? (
                  <>
                    <div>
                      <span className="mono text-foreground">{deps.data.summary.available}</span> of {deps.data.summary.total} available
                    </div>
                    {deps.data.summary.missing_required.length > 0 ? (
                      <div className="text-destructive">Missing required: {deps.data.summary.missing_required.join(', ')}</div>
                    ) : (
                      <div className="text-ok">All core dependencies present.</div>
                    )}
                    {deps.data.summary.missing_optional.length > 0 ? (
                      <div className="text-muted-foreground">Optional, not installed: {deps.data.summary.missing_optional.join(', ')}</div>
                    ) : null}
                  </>
                ) : (
                  <Loading />
                )}
              </PanelBody>
            </Panel>

            <Panel>
              <PanelHeader title="Roadmap" />
              <ol className="divide-y text-xs">
                {ROADMAP.map((r) => (
                  <li key={r.n} className="flex items-center gap-2 px-3 py-1.5">
                    <span className="mono w-5 text-muted-foreground">P{r.n}</span>
                    <span className={cn('flex-1', !r.done && 'text-muted-foreground')}>{r.title}</span>
                    <Badge variant={r.done ? 'ok' : 'outline'}>{r.done ? 'implemented' : 'planned'}</Badge>
                  </li>
                ))}
              </ol>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  )
}
