import { useState } from 'react'


export default function ConfirmDialog({ title, detail, onClose, onConfirm }: { title: string; detail: string; onClose: () => void; onConfirm: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function confirm() {
    setBusy(true)
    setError('')
    try { await onConfirm() }
    catch (problem) { setError((problem as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop" onMouseDown={onClose}><div className="confirm-modal" role="alertdialog" aria-modal="true" aria-label={title} onMouseDown={event => event.stopPropagation()}>
    <h2>{title}</h2><p>{detail}</p><p className="confirm-note">Saved schedules that use this item will be kept and marked “Needs review”.</p>
    {error && <p className="field-error">{error}</p>}
    <div className="modal-actions"><button className="outline-button" onClick={onClose} disabled={busy}>Cancel</button><button className="danger-button" onClick={confirm} disabled={busy}>{busy ? 'Deleting…' : 'Delete'}</button></div>
  </div></div>
}
