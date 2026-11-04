import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import * as React from 'react'

import { useHex } from '@/api/hooks'
import { ErrorNote, Loading } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/input'
import { useUi } from '@/store/ui'
import { cn, hex, parseOffset } from '@/lib/utils'

const WIDTH = 16
const PAGE_SIZES = [256, 512, 1024, 4096]

function byteTone(b: number): string {
  if (b === 0) return 'text-muted-foreground/40'
  if (b === 0xff) return 'text-warn'
  if (b >= 0x20 && b < 0x7f) return 'text-foreground'
  return 'text-info'
}

export interface HexViewerProps {
  evidenceId: string
  totalSize: number
}

/** Windowed hex/ASCII viewer over the immutable original. Reads at most one page at a time from the server. */
export function HexViewer({ evidenceId, totalSize }: HexViewerProps) {
  const pageSize = useUi((s) => s.hexPageSize)
  const setPageSize = useUi((s) => s.setHexPageSize)
  const [offset, setOffset] = React.useState(0)
  const [goto, setGoto] = React.useState('')
  const [gotoError, setGotoError] = React.useState(false)
  const [hover, setHover] = React.useState<number | null>(null)
  const [selected, setSelected] = React.useState<{ offset: number; value: number } | null>(null)

  const { data, error, isPending, isFetching } = useHex(evidenceId, offset, pageSize)
  const lastOffset = Math.max(0, Math.floor((totalSize - 1) / WIDTH) * WIDTH)
  const clamp = (n: number) => Math.min(Math.max(0, Math.floor(n / WIDTH) * WIDTH), lastOffset)

  const jump = (e: React.FormEvent) => {
    e.preventDefault()
    const n = parseOffset(goto)
    if (n === null || n >= totalSize) {
      setGotoError(true)
      return
    }
    setGotoError(false)
    setOffset(clamp(n))
    setSelected(null)
  }

  const end = data ? data.offset + data.length : offset
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-0.5">
          <Button variant="outline" size="icon" aria-label="First page" disabled={offset === 0} onClick={() => setOffset(0)}>
            <ChevronsLeft />
          </Button>
          <Button variant="outline" size="icon" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(clamp(offset - pageSize))}>
            <ChevronLeft />
          </Button>
          <Button variant="outline" size="icon" aria-label="Next page" disabled={offset + pageSize >= totalSize} onClick={() => setOffset(clamp(offset + pageSize))}>
            <ChevronRight />
          </Button>
          <Button variant="outline" size="icon" aria-label="Last page" disabled={offset + pageSize >= totalSize} onClick={() => setOffset(clamp(Math.max(0, totalSize - pageSize)))}>
            <ChevronsRight />
          </Button>
        </div>
        <form onSubmit={jump} className="flex items-center gap-1">
          <Input
            aria-label="Go to offset"
            aria-invalid={gotoError}
            placeholder="go to 0x1a0 / 416"
            className={cn('mono h-7 w-40 text-xs', gotoError && 'border-destructive')}
            value={goto}
            onChange={(e) => {
              setGoto(e.target.value)
              setGotoError(false)
            }}
          />
          <Button type="submit" variant="secondary" size="sm">
            Go
          </Button>
        </form>
        <Select aria-label="Bytes per page" className="h-7 w-36 text-xs" value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
          {PAGE_SIZES.map((n) => (
            <option key={n} value={n}>
              {n} B / page
            </option>
          ))}
        </Select>
        <span className="mono ml-auto text-[11px] text-muted-foreground">
          0x{hex(offset)}–0x{hex(Math.max(end - 1, offset))} of {totalSize.toLocaleString()} B{isFetching && !isPending ? ' · …' : ''}
        </span>
      </div>

      {error ? <ErrorNote error={error} /> : null}
      {isPending ? <Loading label="Reading bytes…" /> : null}

      {data ? (
        <div className="mono overflow-x-auto rounded-md border bg-background p-2 text-[12px] leading-5" role="table" aria-label="Hex dump">
          <div className="flex gap-4 border-b pb-1 text-muted-foreground/70" role="row">
            <span className="w-[68px] shrink-0">offset</span>
            <span className="flex gap-[0.7ch]">
              {Array.from({ length: WIDTH }, (_, i) => (
                <span key={i} className={cn('w-[2ch] text-center', i === 7 && 'mr-[1ch]')}>
                  {i.toString(16).padStart(2, '0')}
                </span>
              ))}
            </span>
            <span>decoded text</span>
          </div>
          {data.rows.map((row) => {
            const bytes = row.hex ? row.hex.split(' ') : []
            return (
              <div key={row.offset} className="flex gap-4" role="row">
                <span className="w-[68px] shrink-0 text-muted-foreground">{hex(row.offset)}</span>
                <span className="flex gap-[0.7ch]">
                  {Array.from({ length: WIDTH }, (_, i) => {
                    const h = bytes[i]
                    const abs = row.offset + i
                    if (h === undefined) return <span key={i} className={cn('w-[2ch]', i === 7 && 'mr-[1ch]')} />
                    const v = parseInt(h, 16)
                    return (
                      <button
                        type="button"
                        key={i}
                        aria-label={`byte at ${abs}`}
                        className={cn(
                          'w-[2ch] cursor-default rounded-[2px] text-center',
                          i === 7 && 'mr-[1ch]',
                          byteTone(v),
                          hover === abs && 'bg-accent',
                          selected?.offset === abs && 'bg-primary/25 text-primary',
                        )}
                        onMouseEnter={() => setHover(abs)}
                        onMouseLeave={() => setHover(null)}
                        onClick={() => setSelected({ offset: abs, value: v })}
                      >
                        {h}
                      </button>
                    )
                  })}
                </span>
                <span className="whitespace-pre">
                  {Array.from(row.ascii).map((ch, i) => {
                    const abs = row.offset + i
                    const v = parseInt(bytes[i] ?? '0', 16)
                    return (
                      <span
                        key={i}
                        className={cn(
                          'rounded-[2px]',
                          ch === '.' ? 'text-muted-foreground/50' : byteTone(v),
                          hover === abs && 'bg-accent',
                          selected?.offset === abs && 'bg-primary/25 text-primary',
                        )}
                        onMouseEnter={() => setHover(abs)}
                        onMouseLeave={() => setHover(null)}
                        onClick={() => setSelected({ offset: abs, value: v })}
                      >
                        {ch}
                      </span>
                    )
                  })}
                </span>
              </div>
            )
          })}
        </div>
      ) : null}

      <div className="mono min-h-5 text-[11px] text-muted-foreground" aria-live="polite">
        {selected ? (
          <>
            offset <span className="text-foreground">0x{hex(selected.offset)}</span> ({selected.offset.toLocaleString()}) · value{' '}
            <span className="text-foreground">0x{selected.value.toString(16).padStart(2, '0')}</span> · {selected.value} ·{' '}
            <span className="text-foreground">{selected.value.toString(2).padStart(8, '0')}</span>
            {selected.value >= 0x20 && selected.value < 0x7f ? <> · '{String.fromCharCode(selected.value)}'</> : null}
          </>
        ) : (
          'Click a byte to inspect it.'
        )}
      </div>
    </div>
  )
}
