import { Trash2 } from 'lucide-react'
import * as React from 'react'

import { useCreateNote, useDeleteNote, useNotes } from '@/api/hooks'
import { ErrorNote, Loading } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { formatDateTime } from '@/lib/utils'

export function NotesPanel({ caseId, evidenceId, readOnly = false }: { caseId: string; evidenceId?: string; readOnly?: boolean }) {
  const notes = useNotes(caseId, evidenceId)
  const create = useCreateNote(caseId)
  const del = useDeleteNote(caseId)
  const [body, setBody] = React.useState('')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!body.trim()) return
    create.mutate({ body: body.trim(), evidence_id: evidenceId }, { onSuccess: () => setBody('') })
  }

  return (
    <div className="space-y-3">
      {!readOnly ? (
        <form onSubmit={submit} className="space-y-2">
          <Textarea aria-label="New note" placeholder={evidenceId ? 'Note about this evidence…' : 'Note about this case…'} value={body} onChange={(e) => setBody(e.target.value)} />
          <div className="flex justify-end">
            <Button type="submit" size="sm" disabled={!body.trim() || create.isPending}>
              Add note
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-xs text-muted-foreground">This case is archived; notes are read-only.</p>
      )}
      <ErrorNote error={create.error ?? del.error} />
      {notes.isPending ? <Loading /> : null}
      {notes.data?.length === 0 ? <p className="text-xs text-muted-foreground">No notes yet.</p> : null}
      <ul className="space-y-2">
        {notes.data?.map((n) => (
          <li key={n.id} className="group rounded-md border bg-background p-2.5">
            <div className="whitespace-pre-wrap text-[13px]">{n.body}</div>
            <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
              <span className="mono">{formatDateTime(n.created_at)}</span>
              {!readOnly ? (
                <Button variant="ghost" size="icon" className="size-6 opacity-0 group-hover:opacity-100 focus-visible:opacity-100" aria-label="Delete note" onClick={() => del.mutate(n.id)}>
                  <Trash2 />
                </Button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
