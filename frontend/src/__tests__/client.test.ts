import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError, artifactUrl, errorFromBody, withQuery } from '@/api/client'

afterEach(() => vi.unstubAllGlobals())

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('errorFromBody', () => {
  it('reads the backend error envelope', () => {
    const e = errorFromBody(409, JSON.stringify({ error: { code: 'case_archived', message: 'This case is archived.', details: [1] } }))
    expect(e).toBeInstanceOf(ApiError)
    expect([e.status, e.code, e.message, e.details]).toEqual([409, 'case_archived', 'This case is archived.', [1]])
  })
  it('falls back gracefully for non-JSON bodies (proxy errors, HTML)', () => {
    const e = errorFromBody(502, '<html>Bad gateway</html>')
    expect(e.status).toBe(502)
    expect(e.code).toBe('http_error')
    expect(e.message).toContain('Bad gateway')
    expect(errorFromBody(500, '').message).toBe('HTTP 500')
  })
})

describe('withQuery', () => {
  it('drops empty values and encodes the rest', () => {
    expect(withQuery('/x', { a: 1, b: '', c: undefined, d: null, e: 'a b', f: false })).toBe('/x?a=1&e=a+b&f=false')
    expect(withQuery('/x', {})).toBe('/x')
    expect(withQuery('/x')).toBe('/x')
  })
})

describe('api()', () => {
  it('sends JSON bodies and returns parsed JSON', async () => {
    const fetchMock = vi.fn(async () => json({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(api('/api/cases', { method: 'POST', json: { name: 'x' } })).resolves.toEqual({ ok: true })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"name":"x"}')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })
  it('throws ApiError carrying the server code for non-2xx responses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ error: { code: 'case_not_found', message: 'Case not found.' } }, 404)))
    await expect(api('/api/cases/x')).rejects.toMatchObject({ name: 'ApiError', status: 404, code: 'case_not_found' })
  })
  it('reports an unreachable server distinctly', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(api('/api/health')).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })
  it('returns undefined for 204', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    await expect(api('/api/notes/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})

describe('artifactUrl', () => {
  it('encodes each path segment but keeps the slashes', () => {
    expect(artifactUrl('job1', 'nested/a b.bin')).toBe('/api/jobs/job1/artifacts/nested/a%20b.bin')
  })
})
