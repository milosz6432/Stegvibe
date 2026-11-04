import type { Evidence } from './types'

/** Error raised for every non-2xx response; mirrors the backend's {"error": {code, message, details}} envelope. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export function errorFromBody(status: number, text: string): ApiError {
  try {
    const body = JSON.parse(text) as { error?: { code?: string; message?: string; details?: unknown } }
    if (body.error) {
      return new ApiError(status, body.error.code ?? 'error', body.error.message ?? `HTTP ${status}`, body.error.details)
    }
  } catch {
    /* not JSON: fall through */
  }
  return new ApiError(status, 'http_error', text.trim().slice(0, 300) || `HTTP ${status}`)
}

type Query = Record<string, string | number | boolean | null | undefined>

export function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `${path}?${s}` : path
}

export async function api<T>(path: string, init: { method?: string; json?: unknown; query?: Query; signal?: AbortSignal } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: string | undefined
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(init.json)
  }
  let res: Response
  try {
    res = await fetch(withQuery(path, init.query), { method: init.method ?? 'GET', headers, body, signal: init.signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'network_error', 'Cannot reach the SPECTRA server. Is the backend running?')
  }
  if (!res.ok) throw errorFromBody(res.status, await res.text())
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export interface UploadHandle {
  promise: Promise<Evidence>
  abort: () => void
}

/** Streams the raw file as the request body (no multipart buffering) and reports upload progress. */
export function uploadEvidence(caseId: string, file: File, onProgress?: (fraction: number) => void): UploadHandle {
  const xhr = new XMLHttpRequest()
  const promise = new Promise<Evidence>((resolve, reject) => {
    xhr.open('POST', withQuery(`/api/cases/${caseId}/evidence`, { filename: file.name }))
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as Evidence)
        } catch {
          reject(new ApiError(xhr.status, 'bad_response', 'The server returned an unreadable response.'))
        }
      } else {
        reject(errorFromBody(xhr.status, xhr.responseText))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, 'network_error', 'Upload failed: cannot reach the SPECTRA server.'))
    xhr.onabort = () => reject(new ApiError(0, 'aborted', 'Upload cancelled.'))
    xhr.send(file)
  })
  return { promise, abort: () => xhr.abort() }
}

export const downloadUrl = (evidenceId: string) => `/api/evidence/${evidenceId}/download`
export const artifactUrl = (jobId: string, name: string) =>
  `/api/jobs/${jobId}/artifacts/${name.split('/').map(encodeURIComponent).join('/')}`
