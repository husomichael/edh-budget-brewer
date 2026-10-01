import { useEffect, useRef, useState } from 'react'
import { searchCommanders } from '../api'
import { colorIdentityLabel } from '../format'
import type { Commander } from '../types'

interface Props {
  value: Commander | null
  onChange: (commander: Commander | null) => void
}

export function CommanderSearch({ value, onChange }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Commander[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      return
    }
    // Debounce, and abort in-flight requests so a fast typist does not get
    // results for a prefix they have already moved past.
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const data = await searchCommanders(query, controller.signal)
        setResults(data.results)
        setOpen(true)
      } catch (error) {
        if ((error as Error).name !== 'AbortError') setResults([])
      } finally {
        setLoading(false)
      }
    }, 200)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  function select(commander: Commander) {
    onChange(commander)
    setQuery('')
    setResults([])
    setOpen(false)
  }

  if (value) {
    return (
      <div className="field">
        <label>Commander</label>
        <div className="selected-commander">
          {value.image_uri && (
            <img src={value.image_uri} alt="" className="commander-thumb" />
          )}
          <div className="selected-commander-text">
            <strong>{value.name}</strong>
            <span className="muted">{value.type_line}</span>
            <span className="muted">
              {colorIdentityLabel(value.color_identity)}
            </span>
          </div>
          <button type="button" className="link" onClick={() => onChange(null)}>
            Change
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="field" ref={boxRef}>
      <label htmlFor="commander">Commander</label>
      <input
        id="commander"
        type="text"
        autoComplete="off"
        placeholder="Start typing a commander name..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
      />
      {loading && <span className="muted small">Searching...</span>}
      {open && results.length > 0 && (
        <ul className="autocomplete">
          {results.map((commander) => (
            <li key={commander.oracle_id}>
              <button type="button" onClick={() => select(commander)}>
                <span>{commander.name}</span>
                <span className="muted small">{commander.type_line}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && !loading && query.trim() && results.length === 0 && (
        <p className="muted small">
          No commanders match. Only legendary creatures and cards that say they
          can be your commander are eligible.
        </p>
      )}
    </div>
  )
}
