import { Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import type { Catalog, Preferences } from '../types'
import ConfirmDialog from './ConfirmDialog'
import CourseFormModal from './CourseFormModal'
import SectionManager from './SectionManager'
import type { Course, CourseInput } from '../types'

export default function CoursesView({ catalog, preferences, onChange, onSave, onChanged = async () => {}, saving, manage = false, generatorActions }: { catalog: Catalog; preferences: Preferences; onChange: (next: Preferences) => void; onSave: () => void; onChanged?: (message: string) => Promise<void>; saving: boolean; manage?: boolean; generatorActions?: ReactNode }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All courses')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [editing, setEditing] = useState<Course | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Course | null>(null)
  const [archived, setArchived] = useState<Course[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [restoring, setRestoring] = useState<number | null>(null)
  const [archiveError, setArchiveError] = useState('')
  useEffect(() => { if (manage) api.archivedCourses().then(setArchived).catch(problem => setArchiveError((problem as Error).message)) }, [manage])
  const filtered = catalog.courses.filter(course => {
    const matchesSearch = `${course.code} ${course.name} ${course.offering_department}`.toLowerCase().includes(query.toLowerCase())
    const isSoftware = /Yazılım Mühendisliği|Software Engineering/i.test(course.offering_department)
    const matchesFilter = filter === 'All courses' || (filter === 'Software Engineering' ? isSoftware : !isSoftware)
    return matchesSearch && matchesFilter
  })
  function toggleCourse(id: number) {
    onChange({ ...preferences, selected_course_ids: preferences.selected_course_ids.includes(id) ? preferences.selected_course_ids.filter(item => item !== id) : [...preferences.selected_course_ids, id] })
  }
  function toggleSection(id: number) {
    onChange({ ...preferences, excluded_section_ids: preferences.excluded_section_ids.includes(id) ? preferences.excluded_section_ids.filter(item => item !== id) : [...preferences.excluded_section_ids, id] })
  }
  async function saveCourse(data: CourseInput) {
    const creating = editing === 'new'
    if (creating) await api.addCourse(data)
    else await api.updateCourse((editing as Course).id, data)
    setEditing(null)
    await onChanged(creating ? `${data.code.toUpperCase()} added` : `${data.code.toUpperCase()} updated`)
  }
  async function deleteCourse() {
    if (!deleting) return
    const result = await api.deleteCourse(deleting.id)
    setExpanded(null)
    setDeleting(null)
    await onChanged(`${deleting.code} deleted${result.removed_from_selection ? ' and removed from your selection' : ''}${result.affected_schedules ? `; ${result.affected_schedules} saved schedule(s) invalidated` : ''}`)
    setArchived(await api.archivedCourses())
  }
  async function restoreCourse(course: Course) {
    setRestoring(course.id)
    setArchiveError('')
    try {
      await api.restoreCourse(course.id)
      await onChanged(`${course.code} restored`)
      setArchived(await api.archivedCourses())
    } catch (problem) {
      setArchiveError((problem as Error).message)
    } finally {
      setRestoring(null)
    }
  }
  return <section className="content-page">
    <div className="content-heading"><div><span className="eyebrow">{catalog.period.toUpperCase()}</span><h1>{manage ? 'Admin Panel' : generatorActions ? 'Schedule Generator' : 'Courses'}</h1><p>{catalog.courses.length} active courses. {manage ? 'Maintain course and section data.' : generatorActions ? 'Select courses, then generate alternatives to compare.' : 'Select courses and review available sections.'}</p></div><div className="course-heading-actions">{manage ? <button className="primary-button" onClick={() => setEditing('new')}><Plus size={15} />Add Course</button> : <div className="selection-total"><strong>{preferences.selected_course_ids.length}</strong><span> courses selected</span></div>}</div></div>
    <div className="course-toolbar"><label className="search-field"><Search size={16} /><input placeholder="Search by code, name, or department" value={query} onChange={event => setQuery(event.target.value)} /></label><select value={filter} onChange={event => setFilter(event.target.value)} aria-label="Offering department"><option>All courses</option><option>Software Engineering</option><option>Other departments</option></select>{manage ? <button className="outline-button" onClick={() => setShowArchived(!showArchived)}>Archived ({archived.length})</button> : <button className="primary-button" onClick={onSave} disabled={saving}>{saving ? 'Saving…' : 'Save selection'}</button>}</div>
    {generatorActions}
    <div className="course-table-wrap"><table className="course-table"><thead><tr>{!manage && <th aria-label="Select course"></th>}<th>Course</th><th>Department</th><th>ECTS</th><th>Credit</th><th>Type</th><th>Sections</th>{manage && <th>Actions</th>}</tr></thead><tbody>{filtered.map(course => <Fragment key={course.id}><tr>{!manage && <td><input type="checkbox" checked={preferences.selected_course_ids.includes(course.id)} onChange={() => toggleCourse(course.id)} aria-label={`Select ${course.name}`} /></td>}<td><strong className="table-code">{course.code}</strong><span className="table-course-name">{course.name}</span></td><td>{course.offering_department}</td><td>{course.ects ?? '—'}</td><td>{course.credit ?? '—'}</td><td>{course.mandatory === null ? '—' : course.mandatory ? 'Mandatory' : 'Elective'}</td><td><button className="text-button" onClick={() => setExpanded(expanded === course.id ? null : course.id)}>{course.sections.length} · {manage ? 'Manage' : 'View'}</button></td>{manage && <td><div className="row-actions"><button aria-label={`Edit ${course.code}`} title="Edit course" onClick={() => setEditing(course)}><Pencil size={15} /></button><button aria-label={`Delete ${course.code}`} title="Delete course" onClick={() => setDeleting(course)}><Trash2 size={15} /></button></div></td>}</tr>{expanded === course.id && <tr key={`${course.id}-sections`}><td colSpan={7}><SectionManager course={course} onChanged={onChanged} excludedSectionIds={preferences.excluded_section_ids} onToggleExclude={toggleSection} editable={manage} /></td></tr>}</Fragment>)}</tbody></table></div>
    {filtered.length === 0 && <p className="empty-message">No courses match your search.</p>}
    {manage && showArchived && <div className="archived-courses"><h2>Archived Courses</h2><p>Deleted course codes remain reserved. Restore a course to recover its sections and sessions.</p>{archiveError && <p className="field-error" role="alert">{archiveError}</p>}{archived.length === 0 ? <p className="empty-message">No archived courses.</p> : archived.map(course => <div className="archived-course" key={course.id}><span><strong>{course.code}</strong> · {course.name} · {course.sections.length} sections</span><button className="outline-button" disabled={restoring !== null} onClick={() => restoreCourse(course)}>{restoring === course.id ? 'Restoring…' : 'Restore'}</button></div>)}</div>}
    {editing && <CourseFormModal key={editing === 'new' ? 'new' : editing.id} course={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} onSubmit={saveCourse} />}
    {deleting && <ConfirmDialog title="Delete Course" detail={`${deleting.code} — ${deleting.name} and all its sections and sessions will leave the active catalogue.${preferences.selected_course_ids.includes(deleting.id) ? ' This course will also be removed from your selection.' : ''}`} onClose={() => setDeleting(null)} onConfirm={deleteCourse} />}
  </section>
}
