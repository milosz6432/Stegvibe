import type { JsonSchema, JsonSchemaProperty } from '@/api/types'
import { Input, Select } from '@/components/ui/input'

type Values = Record<string, unknown>

/** The JSON-schema "type" of a property, looking through nullable anyOf wrappers. */
export function propertyType(p: JsonSchemaProperty): string | undefined {
  if (typeof p.type === 'string') return p.type
  if (Array.isArray(p.type)) return p.type.find((t) => t !== 'null')
  const inner = p.anyOf?.find((a) => a.type !== 'null')
  return inner ? propertyType(inner) : undefined
}

export function defaultsFromSchema(schema: JsonSchema): Values {
  const out: Values = {}
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    if (prop.default !== undefined) out[key] = prop.default
  }
  return out
}

export interface SchemaFormProps {
  schema: JsonSchema
  value: Values
  onChange: (next: Values) => void
}

/** Renders a plugin's JSON-Schema configuration (the same schema the API validates against). */
export function SchemaForm({ schema, value, onChange }: SchemaFormProps) {
  const entries = Object.entries(schema.properties ?? {})
  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">This plugin has no configurable options.</p>
  }
  const set = (key: string, v: unknown) => {
    const next = { ...value }
    if (v === undefined) delete next[key]
    else next[key] = v
    onChange(next)
  }
  return (
    <div className="space-y-3">
      {entries.map(([key, prop]) => {
        const type = propertyType(prop)
        const label = prop.title ?? key
        const id = `cfg-${key}`
        const current = value[key]
        const bounds =
          prop.minimum !== undefined || prop.maximum !== undefined
            ? ` (${prop.minimum ?? '−∞'} – ${prop.maximum ?? '∞'})`
            : ''
        return (
          <div key={key} className="space-y-1">
            <label htmlFor={id} className="label-caps block">
              {label}
              {bounds}
            </label>
            {prop.enum ? (
              <Select id={id} value={String(current ?? '')} onChange={(e) => set(key, e.target.value)}>
                {prop.enum.map((o) => (
                  <option key={String(o)} value={String(o)}>
                    {String(o)}
                  </option>
                ))}
              </Select>
            ) : type === 'boolean' ? (
              <input id={id} type="checkbox" className="size-4 accent-[var(--primary)]" checked={Boolean(current)} onChange={(e) => set(key, e.target.checked)} />
            ) : type === 'integer' || type === 'number' ? (
              <Input
                id={id}
                type="number"
                step={type === 'integer' ? 1 : 'any'}
                min={prop.minimum}
                max={prop.maximum}
                value={current === undefined ? '' : String(current)}
                onChange={(e) => set(key, e.target.value === '' ? undefined : Number(e.target.value))}
              />
            ) : (
              <Input id={id} type="text" value={current === undefined ? '' : String(current)} onChange={(e) => set(key, e.target.value === '' ? undefined : e.target.value)} />
            )}
            {prop.description ? <p className="text-[11px] text-muted-foreground">{prop.description}</p> : null}
          </div>
        )
      })}
    </div>
  )
}
