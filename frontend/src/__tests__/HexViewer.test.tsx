import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HexViewer } from '@/components/HexViewer'

afterEach(() => vi.unstubAllGlobals())

/** Fake backend: serves a 100-byte file whose byte i has value i. */
function stubHexApi() {
  const calls: URL[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input, 'http://localhost')
      calls.push(url)
      const offset = Number(url.searchParams.get('offset'))
      const length = Math.min(Number(url.searchParams.get('length')), 100 - offset)
      const bytes = Array.from({ length }, (_, i) => offset + i)
      const rows = []
      for (let i = 0; i < bytes.length; i += 16) {
        const part = bytes.slice(i, i + 16)
        rows.push({
          offset: offset + i,
          hex: part.map((b) => b.toString(16).padStart(2, '0')).join(' '),
          ascii: part.map((b) => (b >= 0x20 && b < 0x7f ? String.fromCharCode(b) : '.')).join(''),
        })
      }
      return new Response(JSON.stringify({ evidence_id: 'e1', offset, length, total_size: 100, rows }), { status: 200 })
    }),
  )
  return calls
}

function renderViewer() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <HexViewer evidenceId="e1" totalSize={100} />
    </QueryClientProvider>,
  )
}

describe('<HexViewer>', () => {
  it('renders offsets, hex bytes and decoded text from the API', async () => {
    stubHexApi()
    renderViewer()
    expect(await screen.findByRole('table', { name: /hex dump/i })).toBeInTheDocument()
    expect(screen.getByText('00000000')).toBeInTheDocument()
    expect(screen.getByText('00000010')).toBeInTheDocument()
    expect(screen.getByLabelText('byte at 65')).toHaveTextContent('41') // 'A'
    // The whole 100-byte file fits in one page: bytes 0..99 (0x63).
    expect(screen.getByText(/0x00000000–0x00000063 of 100 B/)).toBeInTheDocument()
  })

  it('inspects a clicked byte (hex, decimal, binary, char)', async () => {
    stubHexApi()
    renderViewer()
    await userEvent.click(await screen.findByLabelText('byte at 65'))
    const status = screen.getByText(/offset/i, { selector: 'div' })
    expect(status).toHaveTextContent('0x00000041')
    expect(status).toHaveTextContent('0x41')
    expect(status).toHaveTextContent('01000001')
    expect(status).toHaveTextContent("'A'")
  })

  it('jumps to a hex offset (aligned to the row) and rejects out-of-range input', async () => {
    const calls = stubHexApi()
    renderViewer()
    await screen.findByRole('table')
    const goto = screen.getByLabelText(/go to offset/i)

    await userEvent.type(goto, '0x45{enter}')
    await waitFor(() => expect(calls.at(-1)?.searchParams.get('offset')).toBe('64')) // 0x45 -> row start 0x40
    expect(goto).not.toHaveAttribute('aria-invalid', 'true')

    await userEvent.clear(goto)
    await userEvent.type(goto, '5000{enter}') // beyond a 100-byte file
    expect(goto).toHaveAttribute('aria-invalid', 'true')
    await userEvent.clear(goto)
    await userEvent.type(goto, 'zz{enter}')
    expect(goto).toHaveAttribute('aria-invalid', 'true')
  })

  it('surfaces server errors instead of failing silently', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: { code: 'evidence_file_missing', message: 'Evidence file is missing from the store.' } }), { status: 404 })))
    renderViewer()
    expect(await screen.findByRole('alert')).toHaveTextContent(/missing from the store/i)
  })
})
