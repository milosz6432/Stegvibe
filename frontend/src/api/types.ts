// Mirrors backend/spectra/schemas/*. Keep in sync with the OpenAPI document at /api/openapi.json.

export interface Case {
  id: string
  name: string
  description: string
  archived: boolean
  created_at: string
  updated_at: string
  evidence_count: number
  total_bytes: number
  job_count: number
  finding_count: number
}

export interface Evidence {
  id: string
  case_id: string
  kind: 'original' | 'derived'
  original_filename: string
  declared_extension: string | null
  size_bytes: number
  md5: string
  sha1: string
  sha256: string
  mime_hint: string | null
  detected_format: string | null
  format_confidence: string | null
  parent_id: string | null
  derivation: Record<string, unknown> | null
  imported_at: string
  duplicate_of: string[]
}

export interface HexRow {
  offset: number
  hex: string
  ascii: string
}

export interface HexView {
  evidence_id: string
  offset: number
  length: number
  total_size: number
  rows: HexRow[]
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface JobArtifact {
  name: string
  size_bytes: number
  sha256: string
}

export interface Job {
  id: string
  case_id: string
  evidence_id: string
  plugin_id: string
  plugin_version: string
  config: Record<string, unknown>
  status: JobStatus
  error_code: string | null
  error_message: string | null
  progress: number
  progress_message: string
  timeout_seconds: number
  memory_limit_mb: number
  result: {
    summary?: Record<string, unknown>
    warnings?: string[]
    finding_count?: number
    artifacts?: JobArtifact[]
    diagnostics?: { traceback?: string }
  } | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type FindingKind =
  | 'integrity'
  | 'structural_anomaly'
  | 'statistical_anomaly'
  | 'metadata_observation'
  | 'extracted_payload'
  | 'flag_candidate'
  | 'info'

export type Confidence = 'info' | 'low' | 'medium' | 'high' | 'verified'

export interface Finding {
  id: string
  case_id: string
  evidence_id: string
  job_id: string | null
  plugin_id: string
  plugin_version: string
  kind: FindingKind
  confidence: Confidence
  title: string
  description: string
  location: Record<string, unknown> | null
  data: Record<string, unknown>
  config: Record<string, unknown>
  evidence_sha256: string
  limitations: string | null
  created_at: string
}

export interface FindingPage {
  items: Finding[]
  total: number
}

export interface Note {
  id: string
  case_id: string
  evidence_id: string | null
  body: string
  created_at: string
  updated_at: string
}

export interface AuditEntry {
  seq: number
  ts: string
  actor: string
  action: string
  case_id: string | null
  evidence_id: string | null
  job_id: string | null
  details: Record<string, unknown>
  prev_hash: string
  entry_hash: string
}

export interface AuditVerification {
  valid: boolean
  entries_checked: number
  head_hash: string
  first_invalid_seq: number | null
  reason: string | null
}

export interface DependencyStatus {
  name: string
  kind: 'python' | 'binary'
  available: boolean
  version: string | null
  location: string | null
  required: boolean
  used_in: string[]
  purpose: string
  install_hint: string
  error: string | null
  verified_by_import: boolean
}

export interface DependencyReport {
  summary: { total: number; available: number; missing_required: string[]; missing_optional: string[] }
  deep: boolean
  items: DependencyStatus[]
}

export interface JsonSchemaProperty {
  type?: string | string[]
  title?: string
  description?: string
  default?: unknown
  minimum?: number
  maximum?: number
  enum?: unknown[]
  anyOf?: JsonSchemaProperty[]
}

export interface JsonSchema {
  type?: string
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
}

export interface PluginInfo {
  id: string
  name: string
  version: string
  description: string
  category: string
  supported_formats: string[]
  dependencies: { name: string; kind: string; optional: boolean; purpose: string; status: DependencyStatus }[]
  method: string
  limitations: string[]
  deterministic: boolean
  cpu_heavy: boolean
  available: boolean
  unavailable_reason: string | null
  source: string
  config_schema: JsonSchema
  summary_schema: JsonSchema | null
}

export interface Health {
  status: 'ok' | 'degraded'
  version: string
  database: { ok: boolean; error: string | null; schema_version: number }
  storage: { writable: boolean; error: string | null; free_bytes: number | null }
}

export interface SystemInfo {
  version: string
  schema_version: number
  python: string
  platform: string
  data_dir: string
  offline: boolean
  limits: Record<string, number>
  isolation: { worker_subprocess: boolean; memory_and_cpu_rlimits: boolean; process_group_kill: boolean }
  plugins: number
  plugin_load_errors: { entry_point: string; error: string }[]
}

export interface Stats {
  cases: number
  archived_cases: number
  evidence: number
  evidence_bytes: number
  findings: number
  findings_by_kind: Record<string, number>
  jobs_by_status: Record<string, number>
  audit_entries: number
}
