import { Plus } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useCases, useCreateCase } from '@/api/hooks'
import { Empty, ErrorNote, Loading, PageHeader } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input, Textarea } from '@/components/ui/input'
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/table'
import { formatBytes, formatDateTime } from '@/lib/utils'
import { useUi } from '@/store/ui'

function NewCaseDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const create = useCreateCase()
  const navigate = useNavigate()
  const setActive = useUi((s) => s.setActiveCase)

  React.useEffect(() => {
    if (open) {
      setName('')
      setDescription('')
      create.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New investigation" description="A case groups related evidence, findings, notes and its audit trail.">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              { name: name.trim(), description: description.trim() },
              {
                onSuccess: (c) => {
                  setActive(c.id)
                  onOpenChange(false)
                  navigate(`/investigations/${c.id}`)
                },
              },
            )
          }}
        >
          <Field label="Name">
            <Input autoFocus required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. picoCTF — hidden_in_plain_sight" />
          </Field>
          <Field label="Description (optional)">
            <Textarea maxLength={5000} value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <ErrorNote error={create.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              Create investigation
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Investigations() {
  const [archived, setArchived] = React.useState(false)
  const [open, setOpen] = React.useState(false)
  const cases = useCases(archived)

  return (
    <div>
      <PageHeader
        title="Investigations"
        subtitle="Each case keeps its evidence, findings, notes and audit trail together."
        actions={
          <>
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input type="checkbox" className="accent-[var(--primary)]" checked={archived} onChange={(e) => setArchived(e.target.checked)} />
              Show archived
            </label>
            <Button onClick={() => setOpen(true)}>
              <Plus /> New investigation
            </Button>
          </>
        }
      />
      <div className="p-5">
        <ErrorNote error={cases.error} className="mb-3" />
        {cases.isPending ? <Loading /> : null}
        {cases.data?.length === 0 ? (
          <Panel>
            <Empty title="No investigations yet">Create one, then import media files as read-only evidence.</Empty>
          </Panel>
        ) : null}
        {cases.data && cases.data.length > 0 ? (
          <Panel>
            <Table>
              <THead>
                <tr>
                  <TH>Name</TH>
                  <TH className="w-20 text-right">Evidence</TH>
                  <TH className="w-24 text-right">Size</TH>
                  <TH className="w-20 text-right">Findings</TH>
                  <TH className="w-44">Updated</TH>
                </tr>
              </THead>
              <TBody>
                {cases.data.map((c) => (
                  <TR key={c.id}>
                    <TD>
                      <Link to={`/investigations/${c.id}`} className="font-medium text-foreground hover:text-primary">
                        {c.name}
                      </Link>{' '}
                      {c.archived ? <Badge variant="warn">archived</Badge> : null}
                      {c.description ? <div className="max-w-xl truncate text-xs text-muted-foreground">{c.description}</div> : null}
                    </TD>
                    <TD className="mono text-right">{c.evidence_count}</TD>
                    <TD className="mono text-right">{formatBytes(c.total_bytes)}</TD>
                    <TD className="mono text-right">{c.finding_count}</TD>
                    <TD className="mono text-[12px]">{formatDateTime(c.updated_at)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Panel>
        ) : null}
      </div>
      <NewCaseDialog open={open} onOpenChange={setOpen} />
    </div>
  )
}
