import { Archive, ArchiveRestore, CheckCircle2, CircleAlert, Copy as CopyIcon, Loader2, Trash2, Upload } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { useAudit, useCase, useEvidenceList, useImportEvidence, usePurgeCase, useUpdateCase } from '@/api/hooks'
import { AuditList } from '@/components/AuditList'
import { CopyButton, Empty, ErrorNote, Loading, PageHeader } from '@/components/common'
import { NotesPanel } from '@/components/NotesPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Panel, PanelBody, PanelHeader } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/table'
import { cn, formatBytes, formatDateTime } from '@/lib/utils'
import { useUi } from '@/store/ui'

interface UploadItem {
  key: string
  name: string
  size: number
  progress: number
  status: 'uploading' | 'done' | 'error'
  error?: string
}

function ImportZone({ caseId, disabled }: { caseId: string; disabled: boolean }) {
  const importEv = useImportEvidence(caseId)
  const [items, setItems] = React.useState<UploadItem[]>([])
  const [drag, setDrag] = React.useState(false)
  const inputRef = React.useRef<HTMLInputElement>(null)

  const patch = (key: string, p: Partial<UploadItem>) => setItems((cur) => cur.map((i) => (i.key === key ? { ...i, ...p } : i)))

  const handleFiles = async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      const key = `${Date.now()}-${Math.random().toString(36).slice(2)}`
      setItems((cur) => [...cur, { key, name: file.name, size: file.size, progress: 0, status: 'uploading' }])
      try {
        await importEv.mutateAsync({ file, onProgress: (f) => patch(key, { progress: f }) })
        patch(key, { status: 'done', progress: 1 })
      } catch (e) {
        patch(key, { status: 'error', error: e instanceof Error ? e.message : 'Upload failed' })
      }
    }
  }

  return (
    <div className="space-y-2">
      <div
        className={cn(
          'flex flex-col items-center justify-center gap-1 rounded-md border border-dashed px-4 py-5 text-center transition-colors',
          drag ? 'border-primary bg-primary/5' : 'border-input',
          disabled && 'pointer-events-none opacity-50',
        )}
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          if (e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files)
        }}
      >
        <Upload className="size-5 text-muted-foreground" />
        <div className="text-[13px]">
          Drop files here or{' '}
          <button type="button" className="text-primary hover:underline" onClick={() => inputRef.current?.click()} disabled={disabled}>
            browse
          </button>
        </div>
        <div className="text-[11px] text-muted-foreground">
          Files are hashed while streaming and stored read-only. The original is never modified.
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          aria-label="Import evidence files"
          onChange={(e) => {
            if (e.target.files?.length) void handleFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>
      {items.length > 0 ? (
        <ul className="space-y-1.5">
          {items.map((i) => (
            <li key={i.key} className="rounded-md border bg-background px-2.5 py-1.5 text-xs">
              <div className="flex items-center gap-2">
                {i.status === 'uploading' ? <Loader2 className="size-3.5 animate-spin text-info" /> : i.status === 'done' ? <CheckCircle2 className="size-3.5 text-ok" /> : <CircleAlert className="size-3.5 text-destructive" />}
                <span className="min-w-0 flex-1 truncate">{i.name}</span>
                <span className="mono text-muted-foreground">{formatBytes(i.size)}</span>
              </div>
              {i.status === 'uploading' ? <Progress value={i.progress} className="mt-1.5" /> : null}
              {i.status === 'error' ? <div className="mt-1 text-destructive">{i.error}</div> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function PurgeDialog({ caseId, name, open, onOpenChange }: { caseId: string; name: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const purge = usePurgeCase(caseId)
  const [typed, setTyped] = React.useState('')
  const navigate = useNavigate()
  const active = useUi((s) => s.activeCaseId)
  const setActive = useUi((s) => s.setActiveCase)
  React.useEffect(() => {
    if (open) {
      setTyped('')
      purge.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Permanently delete this investigation?" description="This removes the case, every evidence file, derived data, findings and notes. The audit log keeps a record of what was deleted. This cannot be undone.">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            purge.mutate(typed, {
              onSuccess: () => {
                if (active === caseId) setActive(null)
                onOpenChange(false)
                navigate('/investigations')
              },
            })
          }}
        >
          <Field label={`Type the case name to confirm: ${name}`}>
            <Input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Confirm case name" />
          </Field>
          <ErrorNote error={purge.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={typed !== name || purge.isPending}>
              <Trash2 /> Delete permanently
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function CaseWorkspace() {
  const { caseId } = useParams()
  const c = useCase(caseId)
  const evidence = useEvidenceList(caseId)
  const audit = useAudit({ case_id: caseId, limit: 15 })
  const update = useUpdateCase(caseId ?? '')
  const setActive = useUi((s) => s.setActiveCase)
  const [purgeOpen, setPurgeOpen] = React.useState(false)

  React.useEffect(() => {
    if (c.data) setActive(c.data.id)
  }, [c.data, setActive])

  if (c.isPending) return <Loading />
  if (c.error || !c.data || !caseId) {
    return (
      <div className="p-5">
        <ErrorNote error={c.error ?? new Error('Case not found')} />
        <Link to="/investigations" className="mt-3 inline-block text-xs text-primary hover:underline">
          ← All investigations
        </Link>
      </div>
    )
  }
  const cs = c.data

  return (
    <div>
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            {cs.name} {cs.archived ? <Badge variant="warn">archived · read-only</Badge> : null}
          </span>
        }
        subtitle={cs.description || `Created ${formatDateTime(cs.created_at)}`}
        actions={
          <>
            <Button variant="secondary" size="sm" disabled={update.isPending} onClick={() => update.mutate({ archived: !cs.archived })}>
              {cs.archived ? <ArchiveRestore /> : <Archive />} {cs.archived ? 'Unarchive' : 'Archive'}
            </Button>
            <Button variant="outline" size="sm" className="text-destructive hover:text-destructive" onClick={() => setPurgeOpen(true)}>
              <Trash2 /> Delete…
            </Button>
          </>
        }
      />
      <div className="grid gap-4 p-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <ErrorNote error={update.error} />
          <Panel>
            <PanelHeader title={`Evidence · ${cs.evidence_count} item${cs.evidence_count === 1 ? '' : 's'} · ${formatBytes(cs.total_bytes)}`} />
            <PanelBody>
              <ImportZone caseId={caseId} disabled={cs.archived} />
            </PanelBody>
            {evidence.isPending ? <Loading /> : null}
            <ErrorNote error={evidence.error} className="m-3" />
            {evidence.data?.length === 0 ? <Empty title="No evidence imported yet" /> : null}
            {evidence.data && evidence.data.length > 0 ? (
              <Table>
                <THead>
                  <tr>
                    <TH>File</TH>
                    <TH className="w-24 text-right">Size</TH>
                    <TH className="w-52">SHA-256</TH>
                    <TH className="w-36" title="Preliminary libmagic guess; real identification arrives in Phase 2">
                      Type hint
                    </TH>
                    <TH className="w-40">Imported</TH>
                  </tr>
                </THead>
                <TBody>
                  {evidence.data.map((e) => (
                    <TR key={e.id}>
                      <TD>
                        <Link to={`/investigations/${caseId}/evidence/${e.id}`} className="font-medium hover:text-primary">
                          {e.original_filename}
                        </Link>
                        {e.duplicate_of.length > 0 ? (
                          <Badge variant="warn" className="ml-1.5" title="Identical bytes already imported in this case">
                            <CopyIcon className="size-3" /> duplicate
                          </Badge>
                        ) : null}
                      </TD>
                      <TD className="mono text-right">{formatBytes(e.size_bytes)}</TD>
                      <TD>
                        <span className="mono flex items-center gap-1 text-[12px]">
                          {e.sha256.slice(0, 16)}…
                          <CopyButton text={e.sha256} label="Copy SHA-256" />
                        </span>
                      </TD>
                      <TD className="mono text-[12px] text-muted-foreground">{e.mime_hint ?? '—'}</TD>
                      <TD className="mono text-[12px]">{formatDateTime(e.imported_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : null}
          </Panel>

          <Panel>
            <PanelHeader title="Case activity" />
            {audit.isPending ? <Loading /> : <AuditList entries={audit.data ?? []} />}
          </Panel>
        </div>

        <Panel className="self-start">
          <PanelHeader title="Case notes" />
          <PanelBody>
            <NotesPanel caseId={caseId} readOnly={cs.archived} />
          </PanelBody>
        </Panel>
      </div>
      <PurgeDialog caseId={caseId} name={cs.name} open={purgeOpen} onOpenChange={setPurgeOpen} />
    </div>
  )
}
