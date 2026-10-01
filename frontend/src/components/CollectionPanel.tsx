import { useState } from 'react'
import { RequestError, importCollection } from '../api'
import type { ImportSummary } from '../types'

export function CollectionPanel() {
  const [text, setText] = useState('')
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [summary, setSummary] = useState<ImportSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    setSummary(null)
    try {
      setSummary(await importCollection(text, replace))
    } catch (err) {
      setError(
        err instanceof RequestError ? err.message : 'Import failed.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <h2>Collection</h2>
      <p className="muted small">
        Paste a card list to record what you own. Then tick{' '}
        <em>Cards I own are free</em> when brewing, and the budget becomes new
        money to spend rather than total retail value.
      </p>
      <p className="muted small">
        Quantities, <code>1x</code> prefixes, set codes, collector numbers,
        section headers and comments are all handled. Names that cannot be
        matched are listed back to you rather than silently skipped.
      </p>

      <textarea
        rows={12}
        placeholder={'1 Sol Ring\n1x Arcane Signet\n4 Mountain (LTR) 123\nSkullclamp'}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <label className="check">
        <input
          type="checkbox"
          checked={replace}
          onChange={(e) => setReplace(e.target.checked)}
        />
        <span>
          Replace my whole collection
          <span className="muted small">
            Otherwise these cards are merged into what is already recorded.
          </span>
        </span>
      </label>

      <button
        type="button"
        className="primary"
        onClick={submit}
        disabled={busy || !text.trim()}
      >
        {busy ? 'Importing...' : 'Import'}
      </button>

      {error && <p className="error">{error}</p>}

      {summary && (
        <div className="import-summary">
          <p>{summary.detail}</p>
          <p className="muted small">
            {summary.parsed} lines parsed &middot; {summary.created} added
            &middot; {summary.updated} updated
          </p>
          {summary.unresolved.length > 0 && (
            <details>
              <summary>
                {summary.unresolved.length} unmatched{' '}
                {summary.unresolved.length === 1 ? 'name' : 'names'}
              </summary>
              <ul className="unresolved">
                {summary.unresolved.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
