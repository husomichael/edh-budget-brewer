import { useEffect, useState } from 'react'
import {
  RequestError,
  brew as runBrew,
  getCommanderBySlug,
  getConfig,
} from './api'
import type { BrewSettings } from './components/BrewForm'
import { BrewForm } from './components/BrewForm'
import { CollectionPanel } from './components/CollectionPanel'
import { DeckResults } from './components/DeckResults'
import { Footer } from './components/Footer'
import { Landing } from './components/Landing'
import { UpgradePathView } from './components/UpgradePathView'
import { dollars } from './format'
import { parseShareUrl, syncShareUrl } from './shareUrl'
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
  // null until /api/config/ answers. Fails closed: if the flag cannot be
  // read, assume demo and hide the write UI. Hiding a feature is never a
  // security problem, whereas showing one that 404s is a broken demo.
  const [demoMode, setDemoMode] = useState<boolean | null>(null)
  // Starts true so the warning never flashes on a healthy instance; only a
  // config response that explicitly says otherwise turns it off.
  const [dataReady, setDataReady] = useState(true)
  const [commander, setCommander] = useState<Commander | null>(null)
  const [settings, setSettings] = useState<BrewSettings>(DEFAULT_SETTINGS)
  const [result, setResult] = useState<Brew | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [minimumCents, setMinimumCents] = useState<number | null>(null)

  useEffect(() => {
    let timer: number | undefined
    const poll = () => {
      getConfig().then(
        (config) => {
          setDemoMode(config.demo_mode)
          setDataReady(config.data_ready)
          // Re-check while loading, so the notice clears on its own rather
          // than requiring a reload. ~6.5 min on a 0.1 CPU instance.
          if (!config.data_ready) timer = window.setTimeout(poll, 15_000)
        },
        () => setDemoMode(true),
      )
    }
    poll()
    return () => window.clearTimeout(timer)
  }, [])

  // Restore a shared link: resolve the commander slug, then brew. Runs once,
  // and only when the URL actually carries parameters.
  useEffect(() => {
    const shared = parseShareUrl(window.location.search)
    if (!shared) return

    let cancelled = false
    // Applied before resolving the slug, so a broken link still lands on the
    // budget the sender intended -- pick a commander and it just works.
    const restored = { ...DEFAULT_SETTINGS, ...shared.settings }
    setSettings(restored)

    setBusy(true)
    getCommanderBySlug(shared.commander)
      .then((cmd) => {
        if (cancelled) return
        setCommander(cmd)
        return brewWith(cmd, restored)
      })
      .catch((err) => {
        if (cancelled) return
        setBusy(false)
        // An unresolvable slug must say so. The alternative is a blank page
        // and no way to tell a typo from a card that cannot be a commander.
        setError(
          err instanceof RequestError
            ? err.message
            : 'Could not load that shared link.',
        )
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /**
   * Brew with explicit arguments rather than reading state.
   *
   * Restoring a share URL sets the commander and settings and then brews
   * immediately; reading them from state would use the previous render's
   * values, because setState is asynchronous.
   */
  async function brewWith(cmd: Commander, s: BrewSettings) {
    setBusy(true)
    setError(null)
    setMinimumCents(null)
    try {
      const data = await runBrew({
        commander_oracle_id: cmd.oracle_id,
        budget_cents: Math.round(s.budgetDollars * 100),
        strategy: s.strategy,
        owned_free: demoMode ? false : s.ownedFree,
        lands: s.lands,
        include_upgrade_path: s.includeUpgradePath,
      })
      setResult(data)
      // Only after a successful brew: a URL that reproduces an error is not
      // worth sharing.
      syncShareUrl(cmd.slug, s)
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

  function submit() {
    if (commander) void brewWith(commander, settings)
  }

  /**
   * Run one of the landing page's worked examples.
   *
   * Goes through the same slug resolution a share URL uses, so the examples
   * cannot drift from the thing they are demonstrating.
   */
  async function runExample(slug: string, budgetDollars: number, tier0: boolean) {
    setBusy(true)
    setError(null)
    try {
      const cmd = await getCommanderBySlug(slug)
      const next: BrewSettings = {
        ...DEFAULT_SETTINGS,
        budgetDollars,
        strategy: tier0 ? 'tier0' : 'auto',
      }
      setCommander(cmd)
      setSettings(next)
      await brewWith(cmd, next)
    } catch (err) {
      setBusy(false)
      setError(
        err instanceof RequestError ? err.message : 'Could not load the example.',
      )
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>EDH Budget Brewer</h1>
        {demoMode === false && (
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
        )}
      </header>

      {!dataReady && (
        <div className="notice">
          <strong>Loading card data.</strong> This instance was just deployed
          and is downloading ~34,500 cards from Scryfall. It takes a few
          minutes on a free instance. Brewing will not work until it
          finishes &mdash; this notice clears itself.
        </div>
      )}

      {tab === 'collection' && demoMode === false ? (
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
              demoMode={demoMode !== false}
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
              <Landing onExample={runExample} busy={busy} />
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

      <Footer demoMode={demoMode !== false} />
    </div>
  )
}
