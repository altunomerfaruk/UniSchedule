import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api'
import type { Course, CourseInput } from '../types'


export default function CourseFormModal({ course, onClose, onSubmit }: { course?: Course; onClose: () => void; onSubmit: (data: CourseInput) => Promise<void> }) {
  const [code, setCode] = useState(course?.code ?? '')
  const [name, setName] = useState(course?.name ?? '')
  const [department, setDepartment] = useState(course?.offering_department ?? '')
  const [ects, setEcts] = useState(course?.ects?.toString() ?? '')
  const [credit, setCredit] = useState(course?.credit?.toString() ?? '')
  const [courseType, setCourseType] = useState(course?.mandatory === null || course?.mandatory === undefined ? '' : course.mandatory ? 'mandatory' : 'elective')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const nextErrors: Record<string, string> = {}
    if (!code.trim()) nextErrors.code = 'Course code is required.'
    if (!name.trim()) nextErrors.name = 'Course name is required.'
    if (!department.trim()) nextErrors.offering_department = 'Department is required.'
    if (ects && (!Number.isInteger(Number(ects)) || Number(ects) < 0)) nextErrors.ects = 'Enter a non-negative whole number.'
    if (credit && (!Number.isInteger(Number(credit)) || Number(credit) < 0)) nextErrors.credit = 'Enter a non-negative whole number.'
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    setSaving(true)
    try {
      await onSubmit({ code: code.trim(), name: name.trim(), offering_department: department.trim(), ects: ects === '' ? null : Number(ects), credit: credit === '' ? null : Number(credit), mandatory: courseType === '' ? null : courseType === 'mandatory' })
    } catch (error) {
      if (error instanceof ApiError && error.field) setErrors({ [error.field]: error.message })
      else setErrors({ form: (error as Error).message })
    } finally {
      setSaving(false)
    }
  }

  return <div className="modal-backdrop" onMouseDown={onClose}><form className="form-modal" role="dialog" aria-modal="true" aria-label={course ? `Edit ${course.code}` : 'Add course'} onMouseDown={event => event.stopPropagation()} onSubmit={submit}>
    <div className="form-modal-head"><div><span className="eyebrow">MANAGE COURSES</span><h2>{course ? 'Edit Course' : 'Add Course'}</h2></div><button type="button" className="modal-close" onClick={onClose}>Close</button></div>
    <div className="form-modal-grid">
      <label>Course Code<input autoFocus value={code} onChange={event => setCode(event.target.value)} maxLength={24} /><small className="field-error">{errors.code}</small></label>
      <label>Course Name<input value={name} onChange={event => setName(event.target.value)} maxLength={160} /><small className="field-error">{errors.name}</small></label>
      <label className="full-field">Department<input value={department} onChange={event => setDepartment(event.target.value)} maxLength={160} /><small className="field-error">{errors.offering_department}</small></label>
      <label>ECTS <span className="optional">Optional</span><input type="number" min="0" step="1" value={ects} onChange={event => setEcts(event.target.value)} /><small className="field-error">{errors.ects}</small></label>
      <label>Credit <span className="optional">Optional</span><input type="number" min="0" step="1" value={credit} onChange={event => setCredit(event.target.value)} /><small className="field-error">{errors.credit}</small></label>
      <label className="full-field">Course Type <span className="optional">Optional</span><select value={courseType} onChange={event => setCourseType(event.target.value)}><option value="">Not specified</option><option value="mandatory">Mandatory</option><option value="elective">Elective</option></select></label>
    </div>
    {errors.form && <p className="field-error">{errors.form}</p>}
    <div className="modal-actions"><button type="button" className="outline-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : course ? 'Save changes' : 'Add course'}</button></div>
  </form></div>
}
