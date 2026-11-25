import { useState } from 'react'
import type { Alternative, Section, Session } from '../types'
import { days } from '../types'

const colors = ['blue', 'amber', 'violet', 'mint', 'rose', 'slate']
const minuteOf = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3))
const offset = (value: string) => (minuteOf(value) - 480) * 0.9
const gridTimes = ['08:00', ...Array.from({ length: 11 }, (_, index) => `${String(index + 8).padStart(2, '0')}:40`)]
type Block = { section: Section; sessions: Session[]; color: string; day: number; start: string; end: string }

function displayBlocks(schedule?: Alternative): Block[] {
  const blocks: Block[] = []
  schedule?.sections.forEach((section, courseIndex) => {
    for (const session of section.sessions) {
      const previous = blocks.at(-1)
      if (previous && previous.section.id === section.id && previous.day === session.day &&
        previous.sessions[0].session_type === session.session_type &&
        previous.sessions[0].room_type === session.room_type &&
        minuteOf(session.start_time) - minuteOf(previous.end) <= 10) {
        previous.sessions.push(session)
        previous.end = session.end_time
      } else {
        blocks.push({ section, sessions: [session], color: colors[courseIndex % colors.length], day: session.day, start: session.start_time, end: session.end_time })
      }
    }
  })
  return blocks
}

export default function Timetable({ schedule, scheduleName, loading, hasSelection, period, department, alternativesCount, canChoose, onAlternatives, onGenerate, onSave, saving }: { schedule?: Alternative; scheduleName?: string; loading: boolean; hasSelection: boolean; period: string; department: string; alternativesCount: number; canChoose: boolean; onAlternatives: () => void; onGenerate: () => void; onSave?: () => void; saving: boolean }) {
  const [detail, setDetail] = useState<Block | null>(null)
  const [preview, setPreview] = useState<{ block: Block; x: number; y: number } | null>(null)
  const blocks = displayBlocks(schedule)
  function showPreview(target: HTMLElement, block: Block) {
    const rect = target.getBoundingClientRect()
    setPreview({ block, x: Math.max(8, Math.min(rect.right + 8, window.innerWidth - 230)), y: Math.max(8, Math.min(rect.top, window.innerHeight - 160)) })
  }
  return <section className="timetable-view">
    <div className="page-head"><div><h1>Weekly Schedule</h1><p>{period} · {department}</p></div><span className="fixed-period">Recurring weekly timetable</span></div>
    <div className="calendar-toolbar">
      <span>{scheduleName || 'Monday to Saturday · 08:00–18:30'}</span>
      {schedule && <div className="schedule-actions">
        <button className="alternatives-link" onClick={onAlternatives}>Alternatives{alternativesCount ? ` (${alternativesCount})` : ''}</button>
        {onSave && <button className="outline-button" onClick={onSave} disabled={saving}>{saving ? 'Saving…' : 'Save schedule'}</button>}
      </div>}
    </div>
    <div className="calendar-scroll"><div className="calendar-head"><div className="time-head" />{days.map(day => <div key={day} className="day-head"><strong>{day}</strong></div>)}</div>
      <div className="calendar-body"><div className="time-rail">{gridTimes.map(time => <span key={time} style={{ top: `${offset(time)}px` }}>{time}</span>)}</div>{days.map((day, dayIndex) => <div className="day-column" key={day}>{blocks.filter(block => block.day === dayIndex).map(block => <button key={block.sessions[0].id} className={`class-block ${block.color} ${block.sessions.length === 1 ? 'short' : ''}`} style={{ top: `${offset(block.start)}px`, height: `${Math.max(18, (minuteOf(block.end) - minuteOf(block.start)) * 0.9 - 3)}px` }} onClick={() => { setPreview(null); setDetail(block) }} onMouseEnter={event => showPreview(event.currentTarget, block)} onMouseLeave={() => setPreview(null)} onFocus={event => showPreview(event.currentTarget, block)} onBlur={() => setPreview(null)} aria-label={`${block.section.course_code} ${block.section.course_name}, section ${block.section.label}, ${day} ${block.start} to ${block.end}, ${block.sessions[0].room_type_label}`}><strong>{block.section.course_code}</strong><span>{block.section.course_name}</span><small>Sec {block.section.label} · {block.start}–{block.end}</small><small>{block.sessions[0].classroom || block.sessions[0].room_type_label}</small></button>)}</div>)}{gridTimes.map(time => <div key={time} className="grid-rule" style={{ top: `${offset(time)}px` }} />)}</div>
    </div>
    {!schedule && <div className="calendar-empty">
      <strong role="status">{loading ? 'Generating alternatives…' : 'No schedule selected'}</strong>
      {!loading && <>
        <span>{canChoose ? 'Choose a generated alternative or a saved schedule to view it here.'
          : hasSelection ? 'Generate alternatives for your course selection.'
          : 'Select courses in Schedule Generator to get started.'}</span>
        <button className="outline-button" onClick={canChoose ? onAlternatives : onGenerate}>{canChoose ? 'Open Alternatives' : 'Open Schedule Generator'}</button>
      </>}
    </div>}
    {preview && <div className="class-preview" role="tooltip" style={{ left: preview.x, top: preview.y }}><strong>{preview.block.section.course_code} · {preview.block.section.course_name}</strong><span>Section {preview.block.section.label} · {days[preview.block.day]}</span><span>{preview.block.start}–{preview.block.end} · {preview.block.sessions[0].classroom || preview.block.sessions[0].room_type_label}</span><span>{preview.block.sessions.length} session{preview.block.sessions.length === 1 ? '' : 's'} · {preview.block.sessions[0].session_type}</span>{preview.block.sessions[0].instructor && <span>{preview.block.sessions[0].instructor}</span>}<small>Click for individual sessions</small></div>}
    {detail && <div className="modal-backdrop" onClick={() => setDetail(null)}><div className="detail-modal" role="dialog" aria-modal="true" aria-label="Course details" onClick={event => event.stopPropagation()}><button className="modal-close" onClick={() => setDetail(null)}>Close</button><span className="eyebrow">{detail.section.course_code} · Section {detail.section.label}</span><h2>{detail.section.course_name}</h2><p>Offered by {detail.section.offering_department}</p><div className="detail-list">{detail.sessions.map(session => <div key={session.id}><strong>{days[session.day]}</strong><span>{session.start_time}–{session.end_time}</span><span>{session.classroom || session.room_type_label}{session.instructor ? ` · ${session.instructor}` : ''}</span></div>)}</div></div></div>}
  </section>
}
