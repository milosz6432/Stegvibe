import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB'] as const

/** Binary-prefixed size, e.g. 1536 -> "1.5 KiB". Exact byte count below 1 KiB. */
export function formatBytes(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n < 0) return '—'
  if (n < 1024) return `${n} B`
  let v = n
  let i = 0
  while (v >= 1024 && i < UNITS.length - 1) {
    v /= 1024
    i++
  }
  return `${v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2)} ${UNITS[i]}`
}

export function shortId(id: string | null | undefined, n = 8): string {
  return id ? id.slice(0, n) : '—'
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { hour12: false })
}

export function formatDuration(startIso: string | null, endIso: string | null): string {
  if (!startIso) return '—'
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  const s = Math.max(0, (end - start) / 1000)
  if (s < 1) return `${Math.round(s * 1000)} ms`
  if (s < 60) return `${s.toFixed(1)} s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

/** Parse "0x1f", "1F" (when hex-looking after 0x only) or decimal into a non-negative integer, else null. */
export function parseOffset(text: string): number | null {
  const t = text.trim().toLowerCase()
  if (!t) return null
  const n = /^0x[0-9a-f]+$/.test(t) ? parseInt(t.slice(2), 16) : /^\d+$/.test(t) ? parseInt(t, 10) : NaN
  return Number.isSafeInteger(n) && n >= 0 ? n : null
}

export function hex(n: number, width = 8): string {
  return n.toString(16).padStart(width, '0')
}
