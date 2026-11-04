import { Badge } from '@/components/ui/badge'
import type { Confidence, FindingKind, JobStatus } from '@/api/types'

export const CONFIDENCE_HELP: Record<Confidence, string> = {
  info: 'Informational. No claim about hidden data.',
  low: 'Weak heuristic signal. Frequently a false positive.',
  medium: 'Moderate heuristic signal. Corroborate with another method.',
  high: 'Strong signal, but still not proof of steganography.',
  verified: 'A deterministic check passed (hash compare, CRC, successful parse). Describes the observation, not intent.',
}

const CONF_VARIANT = { info: 'outline', low: 'default', medium: 'warn', high: 'danger', verified: 'ok' } as const

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  return (
    <Badge variant={CONF_VARIANT[confidence]} title={CONFIDENCE_HELP[confidence]}>
      {confidence}
    </Badge>
  )
}

export const KIND_LABEL: Record<FindingKind, string> = {
  integrity: 'Integrity',
  structural_anomaly: 'Structural anomaly',
  statistical_anomaly: 'Statistical anomaly',
  metadata_observation: 'Metadata',
  extracted_payload: 'Extracted payload',
  flag_candidate: 'Flag candidate',
  info: 'Info',
}

export function KindBadge({ kind }: { kind: FindingKind }) {
  return <Badge variant={kind === 'flag_candidate' ? 'primary' : 'outline'}>{KIND_LABEL[kind] ?? kind}</Badge>
}

const STATUS_VARIANT = { queued: 'default', running: 'info', succeeded: 'ok', failed: 'danger', cancelled: 'warn' } as const

export function StatusBadge({ status }: { status: JobStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>
}
