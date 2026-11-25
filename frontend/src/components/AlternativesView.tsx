import type { Alternative } from '../types'
import { days } from '../types'

type Props = {
  alternatives: Alternative[]
  saved: Alternative[]
  activeIndex: number
  activeSavedId: number | null
  onSelect: (index: number) => void
  onSelectSaved: (id: number) => void
  onGenerate: () => void
  busy: boolean
  generating: boolean
  hasSelection: boolean
}

function sectionLabels(schedule: Alternative) {
  return schedule.sections.map(section => `${section.course_code} · ${section.label}`).join(' / ')
}

export default function AlternativesView({ alternatives, saved, activeIndex, activeSavedId, onSelect, onSelectSaved, onGenerate, busy, generating, hasSelection }: Props) {
  return <section className="content-page">
    <div className="content-heading">
      <div><span className="eyebrow">GENERATED RESULTS</span><h1>Alternatives</h1><p>Compare valid options and choose one to open in My Schedule.</p></div>
      {alternatives.length > 0 && <button className="outline-button" onClick={onGenerate}>Schedule Generator</button>}
    </div>
    {!alternatives.length && <div className="empty-state schedule-empty">
      <span role="status">{generating ? 'Generating schedule alternatives…'
        : hasSelection ? 'Generate alternatives for your course selection.'
        : 'Select courses in Schedule Generator to get started.'}</span>
      {!generating && <button className="outline-button" onClick={onGenerate}>Open Schedule Generator</button>}
    </div>}
    <div className="alternative-list">
      {alternatives.map((item, index) => <button key={index} className={`alternative-row ${activeIndex === index ? 'selected' : ''}`} aria-pressed={activeIndex === index} disabled={busy} onClick={() => onSelect(index)}>
        <div className="alternative-name"><span>Option {index + 1}{activeIndex === index ? ' · Selected' : ''}</span><strong>{item.score}% match</strong></div>
        <div className="alternative-metrics">
          <span>{item.total_ects === null ? 'ECTS not provided' : `${item.total_ects} ECTS`}</span>
          <span>{item.campus_days} campus days</span>
          <span>{item.free_days.length ? `${item.free_days.map(day => days[day].slice(0, 3)).join(', ')} free` : 'No free days'}</span>
          <span>{Math.floor(item.gap_minutes / 60)}h {item.gap_minutes % 60}m gaps</span>
          <span>{item.earliest_class}–{item.latest_class}</span>
        </div>
        <small>{sectionLabels(item)}</small>
      </button>)}
    </div>
    {saved.length > 0 && <div className="saved-list">
      <h2>Saved Schedules</h2>
      {saved.map(item => {
        const id = item.id
        const selected = id === activeSavedId
        return <div className="saved-row" key={id}>
          <div><strong>{item.name}</strong><span>{sectionLabels(item)}</span></div>
          <div className="schedule-actions">
            <div className={item.status === 'valid' ? 'valid-status' : 'needs-review'}>
              {item.status === 'valid' ? 'Valid' : item.status === 'invalid' ? 'Invalid' : 'Needs review'}
            </div>
            {item.status === 'valid' && id !== undefined && <button className="outline-button" aria-pressed={selected} disabled={busy} onClick={() => onSelectSaved(id)}>
              {selected ? 'View selected schedule' : 'Use saved schedule'}
            </button>}
          </div>
          {item.invalid_reason && <p>{item.invalid_reason}</p>}
        </div>
      })}
    </div>}
  </section>
}
