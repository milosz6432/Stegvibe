import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Finding } from '@/api/types'
import { ConfidenceBadge } from '@/components/badges'
import { FindingCard } from '@/components/FindingCard'

const finding: Finding = {
  id: 'f1',
  case_id: 'c1',
  evidence_id: 'e1',
  job_id: 'j1',
  plugin_id: 'core.integrity_verify',
  plugin_version: '1.0.0',
  kind: 'integrity',
  confidence: 'verified',
  title: 'Evidence hashes match the import record',
  description: 'MD5, SHA-1 and SHA-256 equal the recorded values.',
  location: null,
  data: { size_bytes: 1088 },
  config: { chunk_size_kib: 1024 },
  evidence_sha256: 'a'.repeat(64),
  limitations: 'Confirms storage integrity only; says nothing about hidden content.',
  created_at: '2026-11-04T16:00:00Z',
}

describe('<FindingCard>', () => {
  it('is collapsed by default and expands to show how to reproduce the finding', async () => {
    render(<FindingCard finding={finding} />)
    expect(screen.getByText(finding.title)).toBeInTheDocument()
    expect(screen.queryByText(/reproduce this finding/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { expanded: false }))
    expect(screen.getByText(/reproduce this finding/i)).toBeInTheDocument()
    expect(screen.getByText('a'.repeat(64))).toBeInTheDocument()
    expect(screen.getByText('{"chunk_size_kib":1024}')).toBeInTheDocument()
    expect(screen.getByText(/says nothing about hidden content/i)).toBeInTheDocument() // limitations are always shown
  })

  it('highlights integrity failures', () => {
    render(<FindingCard finding={{ ...finding, title: 'INTEGRITY FAILURE: stored evidence differs from the import record' }} />)
    expect(screen.getByText(/INTEGRITY FAILURE/)).toHaveClass('text-destructive')
  })
})

describe('<ConfidenceBadge>', () => {
  it('explains what "verified" does and does not mean', () => {
    render(<ConfidenceBadge confidence="verified" />)
    expect(screen.getByText('verified')).toHaveAttribute('title', expect.stringMatching(/deterministic check passed.*not intent/i))
  })
})
