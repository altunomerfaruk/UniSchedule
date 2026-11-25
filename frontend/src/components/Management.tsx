import { Download } from 'lucide-react'
import type { Alternative, Catalog } from '../types'
import { days } from '../types'

export default function Management({ catalog, schedule, onDownload }: { catalog: Catalog; schedule?: Alternative; onDownload: () => void }) {
  const sessionCount = schedule?.sections.reduce((sum, section) => sum + section.sessions.length, 0) ?? 0
  return <aside className="management">
    <div className="student-profile"><div><strong>UniSchedule</strong><span>{catalog.department}</span></div><span className="avatar">F</span></div>
    <div className="fixed-context"><strong>{catalog.period}</strong><span>Single semester course selection</span></div>
    {schedule && <div className="management-actions"><button className="outline-button" onClick={onDownload}><Download size={14} />Download Schedule</button></div>}
    <div className="management-summary"><span className="summary-label">ECTS / credits</span><div className="unknown-value">Not provided in PDF</div><h3>Schedule summary</h3><div className="summary-row"><span>Campus days</span><strong>{schedule ? `${schedule.campus_days} days` : '—'}</strong></div><div className="summary-row"><span>Free days</span><strong>{schedule ? schedule.free_days.map(day => days[day].slice(0, 3)).join(', ') || 'None' : '—'}</strong></div><div className="summary-row"><span>Source sessions</span><strong>{schedule ? sessionCount : '—'}</strong></div><div className="summary-row"><span>Preference match</span><strong className="score-text">{schedule ? `${schedule.score}%` : '—'}</strong></div></div>
    <p className="demo-note">{catalog.source_notice}</p>
  </aside>
}
