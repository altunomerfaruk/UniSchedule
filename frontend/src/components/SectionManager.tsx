import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from '../api'
import type { Course, Section, Session, SessionInput, SessionType } from '../types'
import { days } from '../types'
import ConfirmDialog from './ConfirmDialog'


function SectionForm({ section, onClose, onSave }: { section?: Section; onClose: () => void; onSave: (label: string) => Promise<void> }) {
  const [label, setLabel] = useState(section?.label ?? '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!label.trim()) { setError('Section number is required.'); return }
    setSaving(true)
    try { await onSave(label.trim()) }
    catch (problem) { setError((problem as Error).message) }
    finally { setSaving(false) }
  }
  return <div className="modal-backdrop" onMouseDown={onClose}><form className="form-modal small-modal" role="dialog" aria-modal="true" aria-label={section ? 'Edit section' : 'Add section'} onMouseDown={event => event.stopPropagation()} onSubmit={submit}>
    <div className="form-modal-head"><h2>{section ? 'Edit Section' : 'Add Section'}</h2><button className="modal-close" type="button" onClick={onClose}>Close</button></div>
    <label>Section Number<input autoFocus value={label} maxLength={12} onChange={event => setLabel(event.target.value)} /><small className="field-error">{error}</small></label>
    <div className="modal-actions"><button type="button" className="outline-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : 'Save section'}</button></div>
  </form></div>
}


function SessionForm({ session, onClose, onSave }: { session?: Session; onClose: () => void; onSave: (value: SessionInput) => Promise<void> }) {
  const [day, setDay] = useState(session?.day ?? 0)
  const [startTime, setStartTime] = useState(session?.start_time ?? '08:40')
  const [endTime, setEndTime] = useState(session?.end_time ?? '09:30')
  const [sessionType, setSessionType] = useState<SessionType>(session?.session_type ?? 'lecture')
  const [classroom, setClassroom] = useState(session?.classroom ?? '')
  const [instructor, setInstructor] = useState(session?.instructor ?? '')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (startTime >= endTime) { setErrors({ end_time: 'End time must be after start time.' }); return }
    setErrors({})
    setSaving(true)
    try { await onSave({ day, start_time: startTime, end_time: endTime, session_type: sessionType, classroom: classroom.trim() || null, instructor: instructor.trim() || null }) }
    catch (problem) {
      if (problem instanceof ApiError && problem.field) setErrors({ [problem.field]: problem.message })
      else setErrors({ form: (problem as Error).message })
    } finally { setSaving(false) }
  }
  return <div className="modal-backdrop" onMouseDown={onClose}><form className="form-modal" role="dialog" aria-modal="true" aria-label={session ? 'Edit session' : 'Add session'} onMouseDown={event => event.stopPropagation()} onSubmit={submit}>
    <div className="form-modal-head"><h2>{session ? 'Edit Session' : 'Add Session'}</h2><button className="modal-close" type="button" onClick={onClose}>Close</button></div>
    <div className="form-modal-grid">
      <label>Day<select value={day} onChange={event => setDay(Number(event.target.value))}>{days.map((name, index) => <option key={name} value={index}>{name}</option>)}</select><small className="field-error">{errors.day}</small></label>
      <label>Session Type<select value={sessionType} onChange={event => setSessionType(event.target.value as SessionType)}><option value="lecture">Lecture</option><option value="laboratory">Laboratory</option><option value="online">Online</option><option value="external_training">External Training</option></select><small className="field-error">{errors.session_type}</small></label>
      <label>Start Time<input type="time" value={startTime} onChange={event => setStartTime(event.target.value)} /><small className="field-error">{errors.start_time}</small></label>
      <label>End Time<input type="time" value={endTime} onChange={event => setEndTime(event.target.value)} /><small className="field-error">{errors.end_time}</small></label>
      <label>Classroom <span className="optional">Optional</span><input value={classroom} maxLength={64} onChange={event => setClassroom(event.target.value)} placeholder="Room number or name" /><small className="field-error">{errors.classroom}</small></label>
      <label>Instructor <span className="optional">Optional</span><input value={instructor} maxLength={120} onChange={event => setInstructor(event.target.value)} /><small className="field-error">{errors.instructor}</small></label>
    </div>
    {errors.form && <p className="field-error">{errors.form}</p>}
    <div className="modal-actions"><button type="button" className="outline-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : 'Save session'}</button></div>
  </form></div>
}


export default function SectionManager({ course, onChanged, excludedSectionIds, onToggleExclude, editable = false }: { course: Course; onChanged: (message: string) => Promise<void>; excludedSectionIds: number[]; onToggleExclude: (id: number) => void; editable?: boolean }) {
  const [expanded, setExpanded] = useState<number | null>(course.sections[0]?.id ?? null)
  const [sectionForm, setSectionForm] = useState<Section | 'new' | null>(null)
  const [sessionForm, setSessionForm] = useState<{ section: Section; session?: Session } | null>(null)
  const [deleting, setDeleting] = useState<{ section: Section; session?: Session } | null>(null)

  async function saveSection(label: string) {
    const isNew = sectionForm === 'new'
    const result = isNew ? await api.addSection(course.id, { label }) : await api.updateSection((sectionForm as Section).id, { label })
    setSectionForm(null)
    setExpanded(result.id)
    await onChanged(isNew ? `Section ${label} added` : `Section ${label} updated`)
  }
  async function saveSession(data: SessionInput) {
    if (!sessionForm) return
    if (sessionForm.session) await api.updateSession(sessionForm.session.id, data)
    else await api.addSession(sessionForm.section.id, data)
    setExpanded(sessionForm.section.id)
    setSessionForm(null)
    await onChanged('Session saved')
  }
  async function deleteItem() {
    if (!deleting) return
    if (deleting.session) await api.deleteSession(deleting.session.id)
    else await api.deleteSection(deleting.section.id)
    setDeleting(null)
    await onChanged(deleting.session ? 'Session deleted' : 'Section deleted')
  }

  return <div className="section-manager">
    <div className="section-manager-head"><div><strong>Sections for {course.code}</strong><span>Each section keeps all of its class sessions together.</span></div>{editable && <button className="outline-button" onClick={() => setSectionForm('new')}><Plus size={14} />Add Section</button>}</div>
    {course.sections.length === 0 && <p className="empty-message">No sections available.</p>}
    {course.sections.map(section => <div className="managed-section" key={section.id}>
      <div className="managed-section-head"><button className="section-toggle" onClick={() => setExpanded(expanded === section.id ? null : section.id)}>Section {section.label} <span>{section.sessions.length} sessions</span></button>{!editable && <label className="exclude-section"><input type="checkbox" checked={excludedSectionIds.includes(section.id)} onChange={() => onToggleExclude(section.id)} />Exclude</label>}{editable && <div className="row-actions"><button aria-label={`Edit section ${section.label}`} title="Edit section" onClick={() => setSectionForm(section)}><Pencil size={14} /></button><button aria-label={`Delete section ${section.label}`} title="Delete section" onClick={() => setDeleting({ section })}><Trash2 size={14} /></button></div>}</div>
      {expanded === section.id && <div className="managed-sessions"><div className="session-toolbar"><span>Day and time</span>{editable && <button className="text-button" onClick={() => setSessionForm({ section })}><Plus size={14} />Add Session</button>}</div>
        {section.sessions.length === 0 && <p className="empty-message">No sessions available.</p>}
        {section.sessions.map(session => <div className="managed-session" key={session.id}><div><strong>{days[session.day]} {session.start_time}–{session.end_time}</strong><span>{session.session_type.replace('_', ' ')} · {session.classroom || session.room_type_label}{session.instructor ? ` · ${session.instructor}` : ''}</span></div>{editable && <div className="row-actions"><button aria-label={`Edit session ${session.id}`} title="Edit session" onClick={() => setSessionForm({ section, session })}><Pencil size={14} /></button><button aria-label={`Delete session ${session.id}`} title="Delete session" onClick={() => setDeleting({ section, session })}><Trash2 size={14} /></button></div>}</div>)}
      </div>}
    </div>)}
    {sectionForm && <SectionForm key={sectionForm === 'new' ? 'new' : sectionForm.id} section={sectionForm === 'new' ? undefined : sectionForm} onClose={() => setSectionForm(null)} onSave={saveSection} />}
    {sessionForm && <SessionForm key={sessionForm.session?.id ?? 'new'} session={sessionForm.session} onClose={() => setSessionForm(null)} onSave={saveSession} />}
    {deleting && <ConfirmDialog title={deleting.session ? 'Delete Session' : 'Delete Section'} detail={deleting.session ? `${course.code} section ${deleting.section.label}, ${days[deleting.session.day]} ${deleting.session.start_time}–${deleting.session.end_time} will leave the active timetable.` : `${course.code} section ${deleting.section.label} and its sessions will leave the active catalogue.`} onClose={() => setDeleting(null)} onConfirm={deleteItem} />}
  </div>
}
