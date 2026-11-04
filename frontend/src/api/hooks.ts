import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, uploadEvidence } from './client'
import type {
  AuditEntry,
  AuditVerification,
  Case,
  DependencyReport,
  Evidence,
  FindingPage,
  Health,
  HexView,
  Job,
  Note,
  PluginInfo,
  Stats,
  SystemInfo,
} from './types'

export const qk = {
  health: ['health'] as const,
  info: ['system-info'] as const,
  deps: (deep: boolean) => ['deps', deep] as const,
  stats: ['stats'] as const,
  cases: (archived: boolean) => ['cases', archived] as const,
  case: (id: string) => ['case', id] as const,
  evidenceList: (caseId: string) => ['evidence-list', caseId] as const,
  evidence: (id: string) => ['evidence', id] as const,
  hex: (id: string, offset: number, length: number) => ['hex', id, offset, length] as const,
  jobs: (f: object) => ['jobs', f] as const,
  findings: (f: object) => ['findings', f] as const,
  notes: (caseId: string, evidenceId?: string) => ['notes', caseId, evidenceId ?? null] as const,
  audit: (f: object) => ['audit', f] as const,
  plugins: ['plugins'] as const,
}

const ACTIVE = new Set(['queued', 'running'])

// ---- system ----------------------------------------------------------------------------------
export const useHealth = () =>
  useQuery({ queryKey: qk.health, queryFn: () => api<Health>('/api/health'), refetchInterval: 15_000, retry: false })

export const useSystemInfo = () => useQuery({ queryKey: qk.info, queryFn: () => api<SystemInfo>('/api/system/info') })

export const useDependencies = (deep = false) =>
  useQuery({
    queryKey: qk.deps(deep),
    queryFn: () => api<DependencyReport>('/api/system/dependencies', { query: { deep } }),
    staleTime: 60_000,
  })

export const useRefreshDependencies = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (deep: boolean) => api<DependencyReport>('/api/system/dependencies', { query: { deep, refresh: true } }),
    onSuccess: (data, deep) => qc.setQueryData(qk.deps(deep), data),
  })
}

export const useStats = () => useQuery({ queryKey: qk.stats, queryFn: () => api<Stats>('/api/stats'), refetchInterval: 2_000 })

// ---- cases -----------------------------------------------------------------------------------
export const useCases = (includeArchived = false) =>
  useQuery({
    queryKey: qk.cases(includeArchived),
    queryFn: () => api<Case[]>('/api/cases', { query: { include_archived: includeArchived } }),
  })

export const useCase = (id: string | undefined) =>
  useQuery({ queryKey: qk.case(id ?? ''), queryFn: () => api<Case>(`/api/cases/${id}`), enabled: !!id })

export const useCreateCase = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; description: string }) => api<Case>('/api/cases', { method: 'POST', json: body }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['cases'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
    },
  })
}

export const useUpdateCase = (id: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Pick<Case, 'name' | 'description' | 'archived'>>) =>
      api<Case>(`/api/cases/${id}`, { method: 'PATCH', json: body }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['cases'] })
      void qc.invalidateQueries({ queryKey: qk.case(id) })
      void qc.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}

export const usePurgeCase = (id: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (confirmName: string) => api<void>(`/api/cases/${id}/purge`, { method: 'POST', json: { confirm_name: confirmName } }),
    onSuccess: () => {
      qc.removeQueries({ queryKey: qk.case(id) })
      void qc.invalidateQueries({ queryKey: ['cases'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
      void qc.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}

// ---- evidence --------------------------------------------------------------------------------
export const useEvidenceList = (caseId: string | undefined) =>
  useQuery({
    queryKey: qk.evidenceList(caseId ?? ''),
    queryFn: () => api<Evidence[]>(`/api/cases/${caseId}/evidence`),
    enabled: !!caseId,
  })

export const useEvidence = (id: string | undefined) =>
  useQuery({ queryKey: qk.evidence(id ?? ''), queryFn: () => api<Evidence>(`/api/evidence/${id}`), enabled: !!id })

export const useHex = (id: string | undefined, offset: number, length: number) =>
  useQuery({
    queryKey: qk.hex(id ?? '', offset, length),
    queryFn: () => api<HexView>(`/api/evidence/${id}/hex`, { query: { offset, length } }),
    enabled: !!id,
    placeholderData: keepPreviousData,
    staleTime: Infinity, // the original is immutable
  })

export const useImportEvidence = (caseId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, onProgress }: { file: File; onProgress?: (f: number) => void }) =>
      uploadEvidence(caseId, file, onProgress).promise,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.evidenceList(caseId) })
      void qc.invalidateQueries({ queryKey: qk.case(caseId) })
      void qc.invalidateQueries({ queryKey: ['cases'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
      void qc.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}

// ---- jobs & findings -------------------------------------------------------------------------
export const useJobs = (filter: { case_id?: string; evidence_id?: string; status?: string; limit?: number }) =>
  useQuery({
    queryKey: qk.jobs(filter),
    queryFn: () => api<Job[]>('/api/jobs', { query: filter }),
    // poll quickly only while something is in flight
    refetchInterval: (q) => (q.state.data?.some((j) => ACTIVE.has(j.status)) ? 800 : false),
  })

export const useCreateJob = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { evidence_id: string; plugin_id: string; config: Record<string, unknown>; timeout_seconds?: number; memory_limit_mb?: number }) =>
      api<Job>('/api/jobs', { method: 'POST', json: body }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      void qc.invalidateQueries({ queryKey: qk.stats })
      void qc.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}

export const useCancelJob = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api<Job>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      void qc.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}

export const useFindings = (filter: { case_id?: string; evidence_id?: string; job_id?: string; kind?: string; confidence?: string; limit?: number; offset?: number }) =>
  useQuery({
    queryKey: qk.findings(filter),
    queryFn: () => api<FindingPage>('/api/findings', { query: filter }),
    placeholderData: keepPreviousData,
  })

export const usePlugins = () => useQuery({ queryKey: qk.plugins, queryFn: () => api<PluginInfo[]>('/api/plugins'), staleTime: 60_000 })

// ---- notes & audit ---------------------------------------------------------------------------
export const useNotes = (caseId: string | undefined, evidenceId?: string) =>
  useQuery({
    queryKey: qk.notes(caseId ?? '', evidenceId),
    queryFn: () => api<Note[]>(`/api/cases/${caseId}/notes`, { query: { evidence_id: evidenceId } }),
    enabled: !!caseId,
  })

export const useCreateNote = (caseId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { body: string; evidence_id?: string }) => api<Note>(`/api/cases/${caseId}/notes`, { method: 'POST', json: body }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes', caseId] })
      void qc.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}

export const useDeleteNote = (caseId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (noteId: string) => api<void>(`/api/notes/${noteId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes', caseId] })
      void qc.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}

export const useAudit = (filter: { case_id?: string; evidence_id?: string; job_id?: string; limit?: number }) =>
  useQuery({ queryKey: qk.audit(filter), queryFn: () => api<AuditEntry[]>('/api/audit', { query: filter }), refetchInterval: 10_000 })

export const useVerifyAudit = () => useMutation({ mutationFn: () => api<AuditVerification>('/api/audit/verify') })
