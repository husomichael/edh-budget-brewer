import { useState } from 'react'
import { RequestError, brew as runBrew } from './api'
import type { BrewSettings } from './components/BrewForm'
import { BrewForm } from './components/BrewForm'
import { CollectionPanel } from './components/CollectionPanel'
import { DeckResults } from './components/DeckResults'
import { UpgradePathView } from './components/UpgradePathView'
import { dollars } from './format'
import type { Brew, Commander } from './types'
import './App.css'

type Tab = 'brew' | 'collection'

const DEFAULT_SETTINGS: BrewSettings = {
  budgetDollars: 100,
  strategy: 'auto',
  ownedFree: false,
  lands: 36,
  includeUpgradePath: false,
}

export default function App() {
  const [tab, setTab] = useState<Tab>('brew')
  const [commander, setCommander] = useState<Commander | null>(null)
  const [settings, setSettings] = useState<BrewSettings>(DEFAULT_SETTINGS)
  const [result, setResult] = useState<Brew | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [minimumCents, setMinimumCents] = useState<number | null>(null)

  async function submit() {
    if (!commander) return
    setBusy(true)
    setError(null)
    setMinimumCents(null)
    try {
      const data = await runBrew({
        commander_oracle_id: commander.oracle_id,
        budget_cents: Math.round(settings.budgetDollars * 100),
        strategy: settings.strategy,
        owned_free: settings.ownedFree,
        lands: settings.lands,
        include_upgrade_path: settings.includeUpgradePath,
      })
      setResult(data)
    } catch (err) {
      setResult(null)
      if (err instanceof RequestError) {
        setError(err.message)
        // The API returns the real minimum, so offer it rather than just
        // reporting failure.
        if (err.minimumCents) setMinimumCents(err.minimumCents)
      } else {
        setError('Could not reach the API. Is the Django server running?')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>EDH Budget Brewer</h1>
        <nav>
          <button
            className={tab === 'brew' ? 'tab on' : 'tab'}
            onClick={() => setTab('brew')}
          >
            Brew
          </button>
          <button
            className={tab === 'collection' ? 'tab on' : 'tab'}
            onClick={() => setTab('collection')}
          >
            Collection
          </button>
        </nav>
      </header>

      {tab === 'collection' ? (
        <main className="single">
          <CollectionPanel />
        </main>
      ) : (
        <main className="split">
          <aside>
            <BrewForm
              commander={commander}
              onCommanderChange={setCommander}
              settings={settings}
              onSettingsChange={setSettings}
              onSubmit={submit}
              busy={busy}
            />
          </aside>

          <section className="output">
            {error && (
              <div className="error-panel">
                <p className="error">{error}</p>
                {minimumCents !== null && (
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      setSettings({
                        ...settings,
                        budgetDollars: Math.ceil(minimumCents / 100),
                      })
                      setError(null)
                      setMinimumCents(null)
                    }}
                  >
                    Raise budget to {dollars(minimumCents)}
                  </button>
                )}
              </div>
            )}

            {!error && !result && !busy && (
              <div className="empty">
                <p>Pick a commander and a budget to generate a deck.</p>
                <p className="muted small">
                  Decks are built to be legal and playable at the price you set:
                  a real mana base, enough ramp and interaction, and a sane
                  curve. Expect to land around 80% of the way there and edit
                  from that starting point.
                </p>
              </div>
            )}

            {result && (
              <>
                <DeckResults brew={result} />
                {result.upgrade_path && (
                  <UpgradePathView path={result.upgrade_path} />
                )}
              </>
            )}
          </section>
        </main>
      )}
    </div>
  )
}
