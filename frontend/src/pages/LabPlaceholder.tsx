import { CheckCircle2, Construction, XCircle } from 'lucide-react'

import { useDependencies } from '@/api/hooks'
import { Loading, PageHeader } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Panel, PanelBody, PanelHeader } from '@/components/ui/card'

import type { LabInfo } from './labs'

/** Honest stand-in for a section whose analysis modules do not exist yet. Shows the plan and real dependency readiness. */
export function LabPlaceholder({ lab }: { lab: LabInfo }) {
  const deps = useDependencies()
  const rows = lab.needs.map((n) => deps.data?.items.find((d) => d.name === n)).filter((d) => d !== undefined)
  return (
    <div>
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            {lab.title} <Badge variant="warn">not implemented · Phase {lab.phase}</Badge>
          </span>
        }
        subtitle={lab.summary}
      />
      <div className="grid gap-4 p-5 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Planned for this section" />
          <PanelBody>
            <div className="mb-3 flex items-start gap-2 rounded-md border border-warn/30 bg-warn/5 p-2.5 text-xs text-warn">
              <Construction className="mt-px size-3.5 shrink-0" />
              <span>Nothing in this list is available yet. SPECTRA does not simulate analysis results.</span>
            </div>
            <ul className="list-disc space-y-1.5 pl-4 text-[13px]">
              {lab.planned.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            {lab.caveat ? (
              <p className="mt-3 border-t pt-3 text-xs text-muted-foreground">
                <b className="text-foreground">Known limitation:</b> {lab.caveat}
              </p>
            ) : null}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Dependency readiness on this machine" />
          {deps.isPending ? <Loading /> : null}
          {lab.needs.length === 0 ? <p className="p-3 text-xs text-muted-foreground">No external dependencies planned.</p> : null}
          <ul className="divide-y">
            {rows.map((d) => (
              <li key={d.name} className="flex items-start gap-2 px-3 py-2 text-xs">
                {d.available ? <CheckCircle2 className="mt-px size-3.5 shrink-0 text-ok" /> : <XCircle className="mt-px size-3.5 shrink-0 text-muted-foreground" />}
                <div className="min-w-0 flex-1">
                  <div>
                    <span className="font-medium">{d.name}</span>{' '}
                    <span className="mono text-muted-foreground">{d.available ? d.version ?? '' : 'not installed'}</span>
                  </div>
                  <div className="text-muted-foreground">{d.purpose}</div>
                  {!d.available && d.install_hint ? <code className="text-[11px] text-foreground/80">{d.install_hint}</code> : null}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  )
}
