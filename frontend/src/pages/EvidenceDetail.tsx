import { AlertTriangle, ChevronRight, Copy as CopyIcon, Download, Lock, Play } from 'lucide-react'
import * as React from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { downloadUrl } from '@/api/client'
import { useAudit, useCase, useEvidence, useFindings, useJobs, usePlugins } from '@/api/hooks'
import type { Evidence, PluginInfo } from '@/api/types'
import { AuditList } from '@/components/AuditList'
import { Empty, ErrorNote, HashRow, Loading, PageHeader } from '@/components/common'
import { FindingCard } from '@/components/FindingCard'
import { HexViewer } from '@/components/HexViewer'
import { JobsTable } from '@/components/JobsTable'
import { NotesPanel } from '@/components/NotesPanel'
import { PluginRunDialog } from '@/components/PluginRunDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Panel, PanelBody, PanelHeader } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { supportsFormat } from '@/lib/formats'
import { formatBytes, formatDateTime } from '@/lib/utils'

function Kv({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 border-b py-1.5 last:border-0">
      <dt className="label-caps w-32 shrink-0 pt-px">{k}</dt>
      <dd className="min-w-0 flex-1 break-words text-[13px]">{children}</dd>
    </div>
  )
}

function Overview({ ev, caseId }: { ev: Evidence; caseId: string }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel>
        <PanelHeader title="Identity" />
        <PanelBody>
          <dl>
            <Kv k="File name">{ev.original_filename}</Kv>
            <Kv k="Declared ext.">{ev.declared_extension ? <code>.{ev.declared_extension}</code> : <span className="text-muted-foreground">none</span>}</Kv>
            <Kv k="Size">
              {formatBytes(ev.size_bytes)} <span className="mono text-muted-foreground">({ev.size_bytes.toLocaleString()} bytes)</span>
            </Kv>
            <Kv k="Status">
              <span className="flex items-center gap-1.5">
                <Badge variant="ok">
                  <Lock className="size-3" /> original · read-only
                </Badge>
              </span>
            </Kv>
            <Kv k="Imported">{formatDateTime(ev.imported_at)}</Kv>
            <Kv k="Evidence ID">
              <code className="text-[12px]">{ev.id}</code>
            </Kv>
          </dl>
          <Button asChild variant="secondary" size="sm" className="mt-3">
            <a href={downloadUrl(ev.id)} download={ev.original_filename}>
              <Download /> Download exact original
            </a>
          </Button>
        </PanelBody>
      </Panel>

      <div className="space-y-4">
        <Panel>
          <PanelHeader title="Hashes (computed while importing)" />
          <PanelBody>
            <HashRow label="SHA-256" value={ev.sha256} />
            <HashRow label="SHA-1" value={ev.sha1} />
            <HashRow label="MD5" value={ev.md5} />
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Format" />
          <PanelBody>
            <dl>
              <Kv k="Identified as">
                {ev.detected_format ? (
                  <Badge variant="primary">{ev.detected_format}</Badge>
                ) : (
                  <span className="text-muted-foreground">Not identified yet. Structural format identification arrives in Phase 2.</span>
                )}
              </Kv>
              <Kv k="libmagic hint">
                {ev.mime_hint ? <code className="text-[12px]">{ev.mime_hint}</code> : <span className="text-muted-foreground">unavailable</span>}
                <div className="text-[11px] text-muted-foreground">A quick signature guess from the first 8 KiB. It is not format verification and can be wrong.</div>
              </Kv>
            </dl>
          </PanelBody>
        </Panel>

        {ev.duplicate_of.length > 0 ? (
          <div className="flex gap-2 rounded-md border border-warn/30 bg-warn/5 p-3 text-xs">
            <CopyIcon className="mt-px size-3.5 shrink-0 text-warn" />
            <div>
              <div className="text-warn">Identical bytes were imported more than once in this case.</div>
              <ul className="mt-1 space-y-0.5">
                {ev.duplicate_of.map((id) => (
                  <li key={id}>
                    <Link className="mono text-primary hover:underline" to={`/investigations/${caseId}/evidence/${id}`}>
                      {id}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function PluginCard({ plugin, ev, onRun }: { plugin: PluginInfo; ev: Evidence; onRun: () => void }) {
  const formatOk = supportsFormat(plugin.supported_formats, ev.detected_format)
  const runnable = plugin.available && formatOk
  const reason = !plugin.available ? plugin.unavailable_reason : !formatOk ? (ev.detected_format ? `Does not support ${ev.detected_format}.` : 'Needs a format-identified file (Phase 2).') : null
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[13px] font-medium">{plugin.name}</span>
            <Badge variant="outline">{plugin.category}</Badge>
            <Badge variant={plugin.deterministic ? 'ok' : 'warn'} title={plugin.deterministic ? 'Exact computation: results are deterministic.' : 'Heuristic: results are indications, never proof.'}>
              {plugin.deterministic ? 'exact' : 'heuristic'}
            </Badge>
          </div>
          <div className="mono text-[11px] text-muted-foreground">
            {plugin.id}@{plugin.version}
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">{plugin.description}</p>
        </div>
        <Button size="sm" disabled={!runnable} onClick={onRun} title={reason ?? undefined}>
          <Play /> Run
        </Button>
      </div>
      {reason ? (
        <div className="mt-2 flex items-center gap-1.5 text-[11.5px] text-warn">
          <AlertTriangle className="size-3" /> {reason}
        </div>
      ) : null}
      <details className="mt-2 text-xs">
        <summary className="label-caps cursor-pointer">Method &amp; limitations</summary>
        <p className="mt-1.5 text-muted-foreground">{plugin.method}</p>
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-muted-foreground">
          {plugin.limitations.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}

function AnalysisTab({ ev, onShowFindings }: { ev: Evidence; onShowFindings: () => void }) {
  const plugins = usePlugins()
  const jobs = useJobs({ evidence_id: ev.id, limit: 50 })
  const [running, setRunning] = React.useState<PluginInfo | null>(null)
  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader title="Available analyses" />
        <PanelBody className="grid gap-3 md:grid-cols-2">
          {plugins.isPending ? <Loading /> : null}
          <ErrorNote error={plugins.error} />
          {plugins.data?.map((p) => (
            <PluginCard key={p.id} plugin={p} ev={ev} onRun={() => setRunning(p)} />
          ))}
        </PanelBody>
        <p className="border-t px-3 py-2 text-[11.5px] text-muted-foreground">
          Only integrity verification exists in Phase 1. Steganography-specific analyses ship in later phases as plugins and will appear here automatically.
        </p>
      </Panel>
      <Panel>
        <PanelHeader title="Job history" />
        {jobs.isPending ? <Loading /> : null}
        {jobs.data?.length === 0 ? <Empty title="No analyses run yet" /> : null}
        {jobs.data && jobs.data.length > 0 ? <JobsTable jobs={jobs.data} onShowFindings={onShowFindings} /> : null}
      </Panel>
      {running ? (
        <PluginRunDialog plugin={running} evidenceId={ev.id} open onOpenChange={(o) => !o && setRunning(null)} />
      ) : null}
    </div>
  )
}

function FindingsTab({ evidenceId }: { evidenceId: string }) {
  const findings = useFindings({ evidence_id: evidenceId, limit: 200 })
  if (findings.isPending) return <Loading />
  return (
    <div className="space-y-2">
      <ErrorNote error={findings.error} />
      {findings.data?.items.length === 0 ? (
        <Panel>
          <Empty title="No findings recorded for this evidence">
            This does not mean the file is clean. It only means no analysis that has been run reported anything.
          </Empty>
        </Panel>
      ) : null}
      {findings.data?.items.map((f) => <FindingCard key={f.id} finding={f} />)}
    </div>
  )
}

export function EvidenceDetail() {
  const { caseId, evidenceId } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'overview'
  const ev = useEvidence(evidenceId)
  const c = useCase(caseId)
  const audit = useAudit({ evidence_id: evidenceId, limit: 100 })

  if (ev.isPending) return <Loading />
  if (ev.error || !ev.data || !caseId) {
    return (
      <div className="p-5">
        <ErrorNote error={ev.error ?? new Error('Evidence not found')} />
      </div>
    )
  }
  const e = ev.data
  const setTab = (t: string) => setParams({ tab: t }, { replace: true })

  return (
    <div>
      <PageHeader
        title={e.original_filename}
        subtitle={
          <span className="flex flex-wrap items-center gap-1">
            <Link to="/investigations" className="hover:text-foreground">
              Investigations
            </Link>
            <ChevronRight className="size-3" />
            <Link to={`/investigations/${caseId}`} className="hover:text-foreground">
              {c.data?.name ?? '…'}
            </Link>
            <ChevronRight className="size-3" />
            <span className="mono">{e.sha256.slice(0, 12)}…</span>
          </span>
        }
      />
      <div className="p-5">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="hex">Hex</TabsTrigger>
            <TabsTrigger value="analysis">Analysis</TabsTrigger>
            <TabsTrigger value="findings">Findings</TabsTrigger>
            <TabsTrigger value="notes">Notes</TabsTrigger>
            <TabsTrigger value="audit">Audit trail</TabsTrigger>
          </TabsList>
          <TabsContent value="overview">
            <Overview ev={e} caseId={caseId} />
          </TabsContent>
          <TabsContent value="hex">
            <Panel>
              <PanelBody>
                <HexViewer evidenceId={e.id} totalSize={e.size_bytes} />
              </PanelBody>
            </Panel>
          </TabsContent>
          <TabsContent value="analysis">
            <AnalysisTab ev={e} onShowFindings={() => setTab('findings')} />
          </TabsContent>
          <TabsContent value="findings">
            <FindingsTab evidenceId={e.id} />
          </TabsContent>
          <TabsContent value="notes">
            <Panel>
              <PanelBody>
                <NotesPanel caseId={caseId} evidenceId={e.id} readOnly={c.data?.archived} />
              </PanelBody>
            </Panel>
          </TabsContent>
          <TabsContent value="audit">
            <Panel>{audit.isPending ? <Loading /> : <AuditList entries={audit.data ?? []} />}</Panel>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
