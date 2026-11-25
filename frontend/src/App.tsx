import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, api } from './api'
import AlternativesView from './components/AlternativesView'
import Brand from './components/Brand'
import CoursesView from './components/CoursesView'
import Management from './components/Management'
import PreferencesView from './components/PreferencesView'
import Sidebar from './components/Sidebar'
import Timetable from './components/Timetable'
import type { Alternative, Catalog, Page, Preferences } from './types'
import { days } from './types'

function csv(schedule: Alternative): string {
  const rows = [['Course code', 'Course name', 'Section', 'Day', 'Start', 'End', 'Room type', 'Session type', 'Offering department']]
  for (const section of schedule.sections) for (const session of section.sessions) {
    rows.push([section.course_code, section.course_name, section.label, days[session.day], session.start_time, session.end_time, session.room_type_label, session.session_type, section.offering_department])
  }
  return rows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(',')).join('\r\n')
}

function StartupState({ message, failed = false }: { message: string; failed?: boolean }) {
  return <main className="boot-state">
    <div>
      <p role={failed ? 'alert' : 'status'}>{message}</p>
      {failed && <button className="outline-button" onClick={() => window.location.reload()}>Try again</button>}
    </div>
  </main>
}

const activeSavedKey = 'unischedule:fall-2026:active-saved-schedule'

type ScheduleChoice = { type: 'generated'; index: number } | { type: 'saved'; id: number }
type Operation = 'generate' | 'save-preferences' | 'save-schedule'
type PublicData = { preferences: Preferences; catalog: Catalog; saved: Alternative[] }

function readSavedChoice(): number | null {
  try {
    const id = Number(localStorage.getItem(activeSavedKey))
    return Number.isSafeInteger(id) && id > 0 ? id : null
  } catch {
    return null
  }
}

function rememberSavedChoice(id: number | null) {
  try {
    if (id === null) localStorage.removeItem(activeSavedKey)
    else localStorage.setItem(activeSavedKey, String(id))
  } catch {
    // The current selection still works if storage is unavailable.
  }
}

async function loadPublicData(): Promise<PublicData> {
  // Establish the anonymous visitor first so both requests belong to it.
  const preferences = await api.preferences()
  const [catalog, saved] = await Promise.all([api.catalog(), api.schedules()])
  return { preferences, catalog, saved }
}

function PublicApp() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [alternatives, setAlternatives] = useState<Alternative[]>([])
  const [saved, setSaved] = useState<Alternative[]>([])
  const [choice, setChoice] = useState<ScheduleChoice | null>(null)
  const [page, setPage] = useState<Page>('My Schedule')
  const [operation, setOperation] = useState<Operation | null>(null)
  const [catalogRefreshing, setCatalogRefreshing] = useState(false)
  const [toast, setToast] = useState('')
  const [error, setError] = useState('')
  const latestPreferences = useRef<Preferences | null>(null)
  const draftVersion = useRef(0)
  const catalogRequest = useRef(0)
  const initialData = useRef<Promise<PublicData> | null>(null)

  useEffect(() => {
    let active = true
    initialData.current ??= loadPublicData()
    initialData.current.then(data => {
      if (!active) return
      setCatalog(data.catalog)
      latestPreferences.current = data.preferences
      setPreferences(data.preferences)
      setSaved(data.saved)
      const id = readSavedChoice()
      if (id !== null && data.saved.some(item => item.id === id && item.status === 'valid')) {
        setChoice({ type: 'saved', id })
      } else {
        rememberSavedChoice(null)
      }
    }).catch(err => { if (active) setError((err as Error).message) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(''), 3500)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const current = choice?.type === 'generated'
    ? alternatives[choice.index]
    : choice?.type === 'saved'
      ? saved.find(item => item.id === choice.id && item.status === 'valid')
      : undefined
  const activeIndex = choice?.type === 'generated' ? choice.index : -1
  const activeSavedId = choice?.type === 'saved' ? choice.id : null
  const generating = operation === 'generate'
  const busy = operation !== null || catalogRefreshing

  function clearSelection() {
    setChoice(null)
    rememberSavedChoice(null)
  }

  function changePreferences(next: Preferences) {
    draftVersion.current += 1
    latestPreferences.current = next
    setPreferences(next)
    setAlternatives([])
    clearSelection()
    setError('')
  }

  async function persistPreferences(draft: Preferences, version: number) {
    const updated = await api.updatePreferences(draft)
    if (version === draftVersion.current) {
      latestPreferences.current = updated
      setPreferences(updated)
    }
    setSaved(await api.schedules())
  }

  async function savePreferences() {
    if (!preferences || busy) return
    const version = draftVersion.current
    setOperation('save-preferences')
    setError('')
    try {
      await persistPreferences(preferences, version)
      if (version === draftVersion.current) setToast('Preferences saved')
    } catch (err) {
      if (version === draftVersion.current) setError((err as Error).message)
    } finally {
      setOperation(null)
    }
  }

  async function generate() {
    if (!preferences?.selected_course_ids.length || busy) return
    const version = draftVersion.current
    setOperation('generate')
    setError('')
    setAlternatives([])
    clearSelection()
    try {
      await persistPreferences(preferences, version)
      if (version !== draftVersion.current) return
      const result = await api.generate()
      if (version !== draftVersion.current) return
      setAlternatives(result.alternatives)
      setPage(currentPage => currentPage === 'Schedule Generator' ? 'Alternatives' : currentPage)
      setToast(`${result.alternatives.length} valid schedules generated`)
    } catch (err) {
      if (version === draftVersion.current) setError((err as Error).message)
    } finally {
      setOperation(null)
    }
  }

  function selectAlternative(index: number) {
    if (busy || !alternatives[index]) return
    rememberSavedChoice(null)
    setChoice({ type: 'generated', index })
    setPage('My Schedule')
  }

  function selectSaved(id: number) {
    if (busy || !saved.some(item => item.id === id && item.status === 'valid')) return
    rememberSavedChoice(id)
    setChoice({ type: 'saved', id })
    setPage('My Schedule')
  }

  async function saveSchedule() {
    if (!current || activeIndex < 0 || busy) return
    const version = draftVersion.current
    setOperation('save-schedule')
    setError('')
    try {
      const result = await api.saveSchedule(`Option ${activeIndex + 1}`, current.sections.map(section => section.id))
      setSaved(items => [result, ...items])
      if (version === draftVersion.current && result.id !== undefined) {
        rememberSavedChoice(result.id)
        setChoice({ type: 'saved', id: result.id })
      }
      setToast('Schedule saved')
    } catch (err) {
      if (version === draftVersion.current) setError((err as Error).message)
    } finally {
      setOperation(null)
    }
  }

  function navigate(next: Page) {
    setPage(next)
    if (next === 'Courses' || next === 'Schedule Generator') {
      const request = ++catalogRequest.current
      setCatalogRefreshing(true)
      api.catalog().then(updated => {
        if (request !== catalogRequest.current) return
        setCatalog(updated)
        const draft = latestPreferences.current
        if (!draft) return
        const courseIds = new Set(updated.courses.map(course => course.id))
        const sectionIds = new Set(updated.courses.flatMap(course => course.sections.map(section => section.id)))
        const selected = draft.selected_course_ids.filter(id => courseIds.has(id))
        const excluded = draft.excluded_section_ids.filter(id => sectionIds.has(id))
        if (selected.length !== draft.selected_course_ids.length || excluded.length !== draft.excluded_section_ids.length) {
          changePreferences({ ...draft, selected_course_ids: selected, excluded_section_ids: excluded })
        }
      }).catch(err => {
        if (request === catalogRequest.current) setError((err as Error).message)
      }).finally(() => {
        if (request === catalogRequest.current) setCatalogRefreshing(false)
      })
    }
  }

  function download() {
    if (!current) return
    const blob = new Blob(['\ufeff', csv(current)], { type: 'text/csv;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'unischedule-fall-2026.csv'
    link.click()
    URL.revokeObjectURL(link.href)
    setToast('Schedule downloaded')
  }

  if (!catalog || !preferences) return <StartupState message={error || 'Loading UniSchedule…'} failed={Boolean(error)} />
  const showCalendar = page === 'My Schedule' || page === 'Dashboard'
  const hasSelection = preferences.selected_course_ids.length > 0
  const canChoose = alternatives.length > 0 || saved.some(item => item.status === 'valid')
  const goToGenerator = () => navigate('Schedule Generator')
  const goToAlternatives = () => navigate('Alternatives')
  const generatorActions = <div className="generator-strip">
    <button className="primary-button" disabled={busy || !hasSelection} onClick={generate}>{generating ? 'Generating…' : 'Generate alternatives'}</button>
    <button className="outline-button" onClick={() => navigate('Preferences')}>Adjust preferences</button>
    {!hasSelection && <span>Select at least one course to generate alternatives.</span>}
  </div>

  return <div className="app-shell">
    <Sidebar page={page} onChange={navigate} />
    <main className="main-panel">
      {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError('')}>Dismiss</button></div>}
      {showCalendar && <Timetable
        schedule={current}
        scheduleName={current ? activeIndex >= 0 ? `Option ${activeIndex + 1} · Unsaved` : current.name || 'Saved schedule' : undefined}
        loading={generating}
        hasSelection={hasSelection}
        period={catalog.period}
        department={catalog.department}
        alternativesCount={alternatives.length}
        canChoose={canChoose}
        onAlternatives={goToAlternatives}
        onGenerate={goToGenerator}
        onSave={activeIndex >= 0 ? saveSchedule : undefined}
        saving={operation === 'save-schedule'}
      />}
      {(page === 'Courses' || page === 'Schedule Generator') && <CoursesView
        catalog={catalog}
        preferences={preferences}
        onChange={changePreferences}
        onSave={savePreferences}
        saving={busy}
        generatorActions={page === 'Schedule Generator' ? generatorActions : undefined}
      />}
      {page === 'Preferences' && <PreferencesView value={preferences} onChange={changePreferences} onSave={savePreferences} saving={busy} />}
      {page === 'Alternatives' && <AlternativesView
        alternatives={alternatives}
        saved={saved}
        activeIndex={activeIndex}
        activeSavedId={activeSavedId}
        onSelect={selectAlternative}
        onSelectSaved={selectSaved}
        onGenerate={goToGenerator}
        busy={busy}
        generating={generating}
        hasSelection={hasSelection}
      />}
      {page === 'Settings' && <div className="content-page"><div className="content-heading"><div><span className="eyebrow">FIXED TERM</span><h1>Settings</h1><p>{catalog.department} · {catalog.period}</p></div></div><p className="credit-note">Course information is maintained by the administrator. Your saved schedules remain available for review after catalogue changes.</p></div>}
    </main>
    <Management catalog={catalog} schedule={current} onDownload={download} />
    {toast && <div className="toast" role="status">{toast}</div>}
  </div>
}

function AdminApp() {
  const [checking, setChecking] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [admin, setAdmin] = useState('')
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState(false)
  const [legacyCount, setLegacyCount] = useState(0)
  const [startupError, setStartupError] = useState('')

  useEffect(() => { api.adminMe().then(async account => {
    if (window.location.pathname === '/admin') { window.location.replace('/admin/dashboard'); return }
    setAdmin(account.username)
    const preferenceData = await api.preferences()
    setPreferences(preferenceData)
    setCatalog(await api.catalog())
    setLegacyCount((await api.adminLegacy()).saved_schedules)
  }).catch(problem => {
    if (problem instanceof ApiError && problem.status === 401) {
      if (window.location.pathname !== '/admin') window.location.replace('/admin')
    } else {
      setStartupError((problem as Error).message)
    }
  }).finally(() => setChecking(false)) }, [])
  useEffect(() => { if (toast) { const timeout = window.setTimeout(() => setToast(''), 3500); return () => window.clearTimeout(timeout) } }, [toast])

  async function login(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try { await api.adminLogin(username, password); window.location.replace('/admin/dashboard') }
    catch (problem) { setError((problem as Error).message); setBusy(false) }
  }
  async function logout() {
    setBusy(true)
    try { await api.adminLogout(); window.location.replace('/admin') }
    catch (problem) {
      if (problem instanceof ApiError && problem.status === 401) window.location.replace('/admin')
      else { setError((problem as Error).message); setBusy(false) }
    }
  }
  async function changed(message: string) {
    setCatalog(await api.catalog())
    setPreferences(await api.preferences())
    setToast(message)
  }
  async function claimLegacy() {
    setBusy(true)
    setError('')
    try {
      const result = await api.adminClaimLegacy()
      setLegacyCount(0)
      setPreferences(await api.preferences())
      setToast(`${result.imported} previous schedules imported to this browser`)
    } catch (problem) { setError((problem as Error).message) }
    finally { setBusy(false) }
  }

  if (checking) return <StartupState message="Loading admin area…" />
  if (startupError) return <StartupState message={startupError} failed />
  if (!admin) return <main className="admin-login-page">
    <form className="admin-login" onSubmit={login}>
      <Brand />
      <span className="eyebrow">ADMIN ACCESS</span>
      <h1>Sign in</h1>
      <p>Course catalogue management</p>
      <label>Username<input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required /></label>
      <label>Password<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required /></label>
      {error && <p className="field-error" role="alert">{error}</p>}
      <button className="primary-button" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      <a href="/">Back to schedule</a>
    </form>
  </main>
  if (!catalog || !preferences) return <StartupState message="Loading course catalogue…" />
  return <div className="admin-shell">
    <header className="admin-header">
      <Brand admin />
      <div><span>Signed in as {admin}</span><a href="/">View schedule</a><button className="outline-button" onClick={logout} disabled={busy}>Sign out</button></div>
    </header>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {legacyCount > 0 && <div className="legacy-import"><span>{legacyCount} schedules from the previous single-user version are available for administrator import. Importing will replace this browser's course selection.</span><button className="outline-button" disabled={busy} onClick={claimLegacy}>Import previous schedules</button></div>}
    <CoursesView manage catalog={catalog} preferences={preferences} onChange={setPreferences} onSave={() => {}} onChanged={changed} saving={busy} />
    {toast && <div className="toast" role="status">{toast}</div>}
  </div>
}

export default function App() {
  return window.location.pathname.startsWith('/admin') ? <AdminApp /> : <PublicApp />
}
