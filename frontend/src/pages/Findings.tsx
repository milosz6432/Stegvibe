import * as React from 'react'

import { useCases, useFindings } from '@/api/hooks'
import { CONFIDENCE_HELP, KIND_LABEL } from '@/components/badges'
import { Empty, ErrorNote, Loading, PageHeader } from '@/components/common'
import { FindingCard } from '@/components/FindingCard'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/card'
import { Select } from '@/components/ui/input'
import { useUi } from '@/store/ui'

const PAGE = 50

export function FindingsPage() {
  const activeCase = useUi((s) => s.activeCaseId)
  const cases = useCases(true)
  const [caseId, setCaseId] = React.useState<string>(activeCase ?? '')
  const [kind, setKind] = React.useState('')
  const [confidence, setConfidence] = React.useState('')
  const [limit, setLimit] = React.useState(PAGE)
  const findings = useFindings({ case_id: caseId || undefined, kind: kind || undefined, confidence: confidence || undefined, limit })

  return (
    <div>
      <PageHeader title="Findings" subtitle="Observations produced by analyses, each with the exact plugin, configuration and evidence hash needed to reproduce it." />
      <div className="space-y-3 p-5">
        <div className="rounded-md border border-info/30 bg-info/5 p-2.5 text-xs text-foreground/90">
          A finding is an observation, not a verdict. <b>verified</b> means a deterministic check passed (for example a hash comparison); it never means steganography was proven.
          Heuristic detectors can only report <b>info</b> to <b>high</b>, and an empty list never means a file is clean.
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Select aria-label="Filter by case" className="h-7 w-56 text-xs" value={caseId} onChange={(e) => setCaseId(e.target.value)}>
            <option value="">All cases</option>
            {cases.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <Select aria-label="Filter by kind" className="h-7 w-44 text-xs" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All kinds</option>
            {Object.entries(KIND_LABEL).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </Select>
          <Select aria-label="Filter by confidence" className="h-7 w-40 text-xs" value={confidence} onChange={(e) => setConfidence(e.target.value)}>
            <option value="">Any confidence</option>
            {Object.keys(CONFIDENCE_HELP).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
          <span className="mono ml-auto text-[11px] text-muted-foreground">{findings.data ? `${findings.data.items.length} of ${findings.data.total}` : ''}</span>
        </div>

        <ErrorNote error={findings.error} />
        {findings.isPending ? <Loading /> : null}
        {findings.data?.items.length === 0 ? (
          <Panel>
            <Empty title="No findings match">Run an analysis from an evidence page&apos;s Analysis tab, or relax the filters.</Empty>
          </Panel>
        ) : null}
        <div className="space-y-2">
          {findings.data?.items.map((f) => (
            <FindingCard key={f.id} finding={f} />
          ))}
        </div>
        {findings.data && findings.data.total > findings.data.items.length ? (
          <Button variant="secondary" size="sm" onClick={() => setLimit(limit + PAGE)}>
            Show more
          </Button>
        ) : null}
      </div>
    </div>
  )
}
