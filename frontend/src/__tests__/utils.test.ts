import { describe, expect, it } from 'vitest'

import { supportsFormat } from '@/lib/formats'
import { formatBytes, formatDuration, hex, parseOffset, shortId } from '@/lib/utils'

describe('formatBytes', () => {
  it('uses exact bytes below 1 KiB and binary prefixes above', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1023)).toBe('1023 B')
    expect(formatBytes(1024)).toBe('1.00 KiB')
    expect(formatBytes(1536)).toBe('1.50 KiB')
    expect(formatBytes(5 * 1024 ** 2)).toBe('5.00 MiB')
    expect(formatBytes(2 * 1024 ** 3)).toBe('2.00 GiB')
  })
  it('does not invent values for missing input', () => {
    expect(formatBytes(null)).toBe('—')
    expect(formatBytes(undefined)).toBe('—')
    expect(formatBytes(-1)).toBe('—')
    expect(formatBytes(Number.NaN)).toBe('—')
  })
})

describe('parseOffset', () => {
  it('accepts decimal and 0x-prefixed hex', () => {
    expect(parseOffset('416')).toBe(416)
    expect(parseOffset('0x1a0')).toBe(416)
    expect(parseOffset('  0X1A0 ')).toBe(416)
    expect(parseOffset('0')).toBe(0)
  })
  it('rejects anything ambiguous or invalid', () => {
    for (const bad of ['', 'abc', '1a0', '-5', '1.5', '0x', '0xzz', '1e3']) expect(parseOffset(bad)).toBeNull()
  })
})

describe('misc helpers', () => {
  it('shortId / hex / duration', () => {
    expect(shortId('0123456789abcdef')).toBe('01234567')
    expect(shortId(null)).toBe('—')
    expect(hex(255)).toBe('000000ff')
    expect(hex(255, 2)).toBe('ff')
    expect(formatDuration(null, null)).toBe('—')
    expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-01T00:00:00.250Z')).toBe('250 ms')
    expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-01T00:00:12Z')).toBe('12.0 s')
    expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-01T00:02:05Z')).toBe('2m 5s')
  })
})

describe('supportsFormat (mirrors backend/spectra/formats.py)', () => {
  it('wildcard works even for unidentified evidence; specific tokens do not', () => {
    expect(supportsFormat(['*'], null)).toBe(true)
    expect(supportsFormat(['png'], null)).toBe(false)
    expect(supportsFormat(['image:*'], null)).toBe(false)
  })
  it('matches exact ids and category wildcards', () => {
    expect(supportsFormat(['png', 'jpeg'], 'png')).toBe(true)
    expect(supportsFormat(['png'], 'jpeg')).toBe(false)
    expect(supportsFormat(['image:*'], 'webp')).toBe(true)
    expect(supportsFormat(['image:*'], 'wav')).toBe(false)
    expect(supportsFormat(['audio:*', 'png'], 'flac')).toBe(true)
  })
})
