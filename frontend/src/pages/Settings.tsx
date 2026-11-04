import { CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import * as React from 'react'

import { useDependencies, usePlugins, useRefreshDependencies, useSystemInfo } from '@/api/hooks'
import { ErrorNote, Loading, PageHeader } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Panel, PanelBody, PanelHeader } from '@/components/ui/card'
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/table'
import { formatBytes } from '@/lib/utils'

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-3 border-b py-1.5 text-[13px] last:border-0">
      <dt className="label-caps w-52 shrink-0 pt-px">{k}</dt>
      <dd className="mono min-w-0 flex-1 break-all text-[12.5px]">{v}</dd>
    </div>
  )
}

export function SettingsPage() {
  const info = useSystemInfo()
  const [deep, setDeep] = React.useState(false)
  const deps = useDependencies(deep)
  const refresh = useRefreshDependencies()
  const plugins = usePlugins()

  return (
    <div>
      <PageHeader title="Settings" subtitle="System information, dependency availability and installed analysis plugins. Server limits are set with SPECTRA_* environment variables." />
      <div className="space-y-4 p-5">
        <Panel>
          <PanelHeader title="System" />
          <PanelBody>
            {info.isPending ? <Loading /> : null}
            <ErrorNote error={info.error} />
            {info.data ? (
              <dl>
                <Row k="Version" v={`${info.data.version} (schema v${info.data.schema_version})`} />
                <Row k="Python" v={info.data.python} />
                <Row k="Platform" v={info.data.platform} />
                <Row k="Data directory" v={info.data.data_dir} />
                <Row k="Network" v={info.data.offline ? 'offline: the server makes no outbound connections' : 'outbound connections enabled'} />
                <Row k="Max upload" v={formatBytes(info.data.limits.max_upload_bytes)} />
                <Row k="Concurrent jobs" v={info.data.limits.max_concurrent_jobs} />
                <Row k="Job time limit" v={`${info.data.limits.default_job_timeout_seconds} s default · ${info.data.limits.max_job_timeout_seconds} s max`} />
                <Row k="Job memory limit" v={info.data.limits.default_job_memory_limit_mb ? `${info.data.limits.default_job_memory_limit_mb} MiB` : 'unlimited'} />
                <Row
                  k="Worker isolation"
                  v={
                    <span className="flex flex-wrap gap-1.5 font-sans">
                      <Badge variant="ok">subprocess per job</Badge>
                      <Badge variant={info.data.isolation.memory_and_cpu_rlimits ? 'ok' : 'warn'}>{info.data.isolation.memory_and_cpu_rlimits ? 'memory/CPU rlimits' : 'no rlimits on this OS'}</Badge>
                      <Badge variant={info.data.isolation.process_group_kill ? 'ok' : 'warn'}>{info.data.isolation.process_group_kill ? 'process-group kill' : 'helper processes may outlive a cancelled job'}</Badge>
                    </span>
                  }
                />
              </dl>
            ) : null}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader
            title="Dependencies"
            actions={
              <>
                <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground" title="Import each Python package in a throw-away subprocess to prove it actually loads">
                  <input type="checkbox" className="accent-[var(--primary)]" checked={deep} onChange={(e) => setDeep(e.target.checked)} /> verify imports
                </label>
                <Button variant="secondary" size="sm" disabled={refresh.isPending} onClick={() => refresh.mutate(deep)}>
                  <RefreshCw className={refresh.isPending ? 'animate-spin' : ''} /> Re-check
                </Button>
              </>
            }
          />
          {deps.isPending ? <Loading /> : null}
          <ErrorNote error={deps.error ?? refresh.error} className="m-3" />
          {deps.data ? (
            <Table>
              <THead>
                <tr>
                  <TH className="w-48">Name</TH>
                  <TH className="w-24">Status</TH>
                  <TH className="w-48">Version</TH>
                  <TH>Purpose / how to install</TH>
                  <TH className="w-32">Needed in</TH>
                </tr>
              </THead>
              <TBody>
                {deps.data.items.map((d) => (
                  <TR key={d.name}>
                    <TD>
                      <span className="font-medium">{d.name}</span>{' '}
                      <span className="text-[11px] text-muted-foreground">{d.kind}</span>
                      {d.required ? <Badge variant="primary" className="ml-1">core</Badge> : null}
                    </TD>
                    <TD>
                      {d.available ? (
                        <span className="flex items-center gap-1 text-ok">
                          <CheckCircle2 className="size-3.5" /> available
                        </span>
                      ) : (
                        <span className={d.required ? 'flex items-center gap-1 text-destructive' : 'flex items-center gap-1 text-muted-foreground'}>
                          <XCircle className="size-3.5" /> missing
                        </span>
                      )}
                    </TD>
                    <TD className="mono max-w-0 truncate text-[11.5px]" title={d.version ?? undefined}>
                      {d.version ?? '—'}
                    </TD>
                    <TD className="text-xs">
                      <div className="text-muted-foreground">{d.purpose}</div>
                      {!d.available ? (
                        <div className="mt-0.5">
                          {d.error ? <span className="text-destructive/90">{d.error}. </span> : null}
                          {d.install_hint ? <code className="text-[11.5px] text-foreground/80">{d.install_hint}</code> : null}
                        </div>
                      ) : null}
                    </TD>
                    <TD className="mono text-[11px] text-muted-foreground">{d.used_in.join(', ')}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : null}
        </Panel>

        <Panel>
          <PanelHeader title={`Analysis plugins${plugins.data ? ` · ${plugins.data.length}` : ''}`} />
          <PanelBody className="space-y-3">
            {plugins.isPending ? <Loading /> : null}
            <ErrorNote error={plugins.error} />
            {info.data?.plugin_load_errors.map((e) => (
              <div key={e.entry_point} className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                Plugin entry point <b>{e.entry_point}</b> failed to load: {e.error}
              </div>
            ))}
            {plugins.data?.map((p) => (
              <div key={p.id} className="rounded-md border bg-background p-3 text-xs">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[13px] font-medium">{p.name}</span>
                  <span className="mono text-muted-foreground">
                    {p.id}@{p.version}
                  </span>
                  <Badge variant={p.available ? 'ok' : 'danger'}>{p.available ? 'available' : 'unavailable'}</Badge>
                  <Badge variant={p.deterministic ? 'ok' : 'warn'}>{p.deterministic ? 'exact' : 'heuristic'}</Badge>
                  <span className="text-muted-foreground">formats: {p.supported_formats.join(', ')}</span>
                </div>
                {p.unavailable_reason ? <div className="mt-1 text-destructive">{p.unavailable_reason}</div> : null}
                <p className="mt-1.5 text-muted-foreground">{p.description}</p>
                <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-muted-foreground">
                  {p.limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            ))}
          </PanelBody>
        </Panel>
      </div>
    </div>
  )
}
