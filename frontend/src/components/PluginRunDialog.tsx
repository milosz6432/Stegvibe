import { Play } from 'lucide-react'
import * as React from 'react'

import { useCreateJob } from '@/api/hooks'
import type { PluginInfo } from '@/api/types'
import { ErrorNote } from '@/components/common'
import { defaultsFromSchema, SchemaForm } from '@/components/SchemaForm'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input } from '@/components/ui/input'

export function PluginRunDialog({ plugin, evidenceId, open, onOpenChange }: { plugin: PluginInfo; evidenceId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [config, setConfig] = React.useState<Record<string, unknown>>(() => defaultsFromSchema(plugin.config_schema))
  const [timeout, setTimeoutS] = React.useState('')
  const [memory, setMemory] = React.useState('')
  const create = useCreateJob()

  React.useEffect(() => {
    if (open) {
      setConfig(defaultsFromSchema(plugin.config_schema))
      create.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, plugin.id])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    create.mutate(
      {
        evidence_id: evidenceId,
        plugin_id: plugin.id,
        config,
        ...(timeout ? { timeout_seconds: Number(timeout) } : {}),
        ...(memory ? { memory_limit_mb: Number(memory) } : {}),
      },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={plugin.name} description={`${plugin.id}@${plugin.version}`}>
        <form onSubmit={submit} className="space-y-4">
          <p className="text-xs text-muted-foreground">{plugin.method}</p>
          <SchemaForm schema={plugin.config_schema} value={config} onChange={setConfig} />
          <details className="rounded-md border p-2">
            <summary className="label-caps cursor-pointer">Resource limits (optional)</summary>
            <div className="mt-2 grid grid-cols-2 gap-3">
              <Field label="Timeout (s)" hint="Server default applies if empty">
                <Input type="number" min={1} value={timeout} onChange={(e) => setTimeoutS(e.target.value)} />
              </Field>
              <Field label="Memory (MiB)" hint="0 = unlimited; min 256">
                <Input type="number" min={0} value={memory} onChange={(e) => setMemory(e.target.value)} />
              </Field>
            </div>
          </details>
          <ErrorNote error={create.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              <Play /> Run analysis
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
