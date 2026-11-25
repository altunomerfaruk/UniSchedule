import { BookOpen, CalendarDays, CalendarRange, LayoutDashboard, ListFilter, Settings2, SlidersHorizontal } from 'lucide-react'
import type { Page } from '../types'
import Brand from './Brand'

const entries: { label: Page; icon: typeof CalendarDays }[] = [
  { label: 'Dashboard', icon: LayoutDashboard }, { label: 'Courses', icon: BookOpen },
  { label: 'Schedule Generator', icon: CalendarRange }, { label: 'My Schedule', icon: CalendarDays },
  { label: 'Alternatives', icon: ListFilter }, { label: 'Preferences', icon: SlidersHorizontal },
  { label: 'Settings', icon: Settings2 },
]

export default function Sidebar({ page, onChange }: { page: Page; onChange: (page: Page) => void }) {
  return <aside className="sidebar">
    <Brand />
    <nav className="nav-list" aria-label="Main navigation">{entries.map(({ label, icon: Icon }) => <button key={label} className={`nav-link ${page === label ? 'active' : ''}`} aria-label={label} aria-current={page === label ? 'page' : undefined} onClick={() => onChange(label)}><Icon size={15} strokeWidth={1.8} /><span>{label}</span></button>)}</nav>
    <div className="sidebar-foot">2026–2027 Fall</div>
  </aside>
}
