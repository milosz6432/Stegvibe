import {
  AudioWaveform,
  FileText,
  Film,
  Flag,
  FolderSearch,
  Image as ImageIcon,
  LayoutDashboard,
  ListChecks,
  PackageOpen,
  Settings as SettingsIcon,
  Tags,
  type LucideIcon,
} from 'lucide-react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useCases, useHealth, useStats } from '@/api/hooks'
import { Select } from '@/components/ui/input'
import { cn, formatBytes } from '@/lib/utils'
import { useUi } from '@/store/ui'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  /** Roadmap phase in which this section becomes functional. Absent = available now. */
  phase?: number
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Workspace',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/investigations', label: 'Investigations', icon: FolderSearch },
    ],
  },
  {
    group: 'Labs',
    items: [
      { to: '/image', label: 'Image Lab', icon: ImageIcon, phase: 3 },
      { to: '/audio', label: 'Audio Lab', icon: AudioWaveform, phase: 4 },
      { to: '/video', label: 'Video Lab', icon: Film, phase: 5 },
      { to: '/metadata', label: 'Metadata Explorer', icon: Tags, phase: 2 },
      { to: '/payload', label: 'Payload Extractor', icon: PackageOpen, phase: 7 },
      { to: '/ctf', label: 'CTF Flag Hunter', icon: Flag, phase: 6 },
    ],
  },
  {
    group: 'Review',
    items: [
      { to: '/findings', label: 'Findings', icon: ListChecks },
      { to: '/reports', label: 'Reports', icon: FileText, phase: 8 },
    ],
  },
]

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 px-4 py-3.5" aria-label="SPECTRA home">
      <svg viewBox="0 0 32 32" className="size-7 shrink-0" aria-hidden="true">
        <rect width="32" height="32" rx="6" fill="var(--card)" stroke="var(--border)" />
        <path d="M3 16h4l3-9 5 18 4-14 3 5h7" fill="none" stroke="var(--primary)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="leading-tight">
        <div className="text-[13px] font-semibold tracking-[0.22em]">SPECTRA</div>
        <div className="text-[10px] text-muted-foreground">stego analysis workbench</div>
      </div>
    </Link>
  )
}

function SideLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end}
      title={item.phase ? `${item.label} — arrives in Phase ${item.phase}` : item.label}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-2.5 px-4 py-1.5 text-[13px] text-muted-foreground hover:bg-accent/60 hover:text-foreground',
          isActive && 'bg-accent/70 text-foreground before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:rounded-r before:bg-primary',
        )
      }
    >
      <Icon className="size-4 shrink-0" />
      <span className="flex-1 truncate">{item.label}</span>
      {item.phase ? <span className="mono rounded-sm border px-1 text-[9.5px] text-muted-foreground/80">P{item.phase}</span> : null}
    </NavLink>
  )
}

function TopBar() {
  const cases = useCases(false)
  const active = useUi((s) => s.activeCaseId)
  const setActive = useUi((s) => s.setActiveCase)
  const navigate = useNavigate()
  const valid = cases.data?.some((c) => c.id === active) ? active : ''
  return (
    <header className="flex h-11 items-center gap-3 border-b bg-card/60 px-4">
      <span className="label-caps">Active case</span>
      <Select
        aria-label="Active case"
        className="h-7 w-64 text-xs"
        value={valid ?? ''}
        onChange={(e) => {
          const id = e.target.value || null
          setActive(id)
          if (id) navigate(`/investigations/${id}`)
        }}
      >
        <option value="">— none selected —</option>
        {cases.data?.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </Select>
      <span className="ml-auto text-[11px] text-muted-foreground">Evidence never leaves this machine.</span>
    </header>
  )
}

function StatusBar() {
  const health = useHealth()
  const stats = useStats()
  const up = health.data?.status === 'ok'
  const jobs = stats.data?.jobs_by_status ?? {}
  const active = (jobs.running ?? 0) + (jobs.queued ?? 0)
  return (
    <footer className="mono flex h-7 items-center gap-4 border-t bg-card/60 px-4 text-[11px] text-muted-foreground" role="contentinfo">
      <span className="flex items-center gap-1.5" title={health.error ? 'Cannot reach the backend' : health.data?.database.error ?? 'Backend healthy'}>
        <span className={cn('size-1.5 rounded-full', health.isPending ? 'bg-muted-foreground' : up ? 'bg-ok' : 'bg-destructive')} />
        {health.isPending ? 'connecting…' : up ? `api ok · v${health.data?.version}` : health.data ? 'api degraded' : 'api unreachable'}
      </span>
      <span>offline</span>
      <span>{active > 0 ? `${active} job${active === 1 ? '' : 's'} active` : 'idle'}</span>
      <span className="ml-auto">
        {stats.data ? `${stats.data.evidence} evidence · ${formatBytes(stats.data.evidence_bytes)} · ${stats.data.audit_entries} audit entries` : ''}
      </span>
    </footer>
  )
}

export function AppShell() {
  return (
    <div className="grid h-full grid-cols-[224px_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)_auto]">
      <aside className="row-span-3 flex flex-col overflow-y-auto border-r bg-card/40">
        <Logo />
        <nav className="flex-1 pb-3" aria-label="Main">
          {NAV.map((g) => (
            <div key={g.group} className="mt-3">
              <div className="label-caps px-4 pb-1">{g.group}</div>
              {g.items.map((item) => (
                <SideLink key={item.to} item={item} />
              ))}
            </div>
          ))}
        </nav>
        <div className="border-t py-2">
          <SideLink item={{ to: '/settings', label: 'Settings', icon: SettingsIcon }} />
        </div>
      </aside>
      <TopBar />
      <main className="min-h-0 overflow-y-auto">
        <Outlet />
      </main>
      <StatusBar />
    </div>
  )
}
