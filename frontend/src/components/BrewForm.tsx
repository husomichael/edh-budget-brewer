import type { Commander } from '../types'
import { CommanderSearch } from './CommanderSearch'

export interface BrewSettings {
  budgetDollars: number
  strategy: 'auto' | 'tier0'
  ownedFree: boolean
  lands: number
  includeUpgradePath: boolean
}

interface Props {
  commander: Commander | null
  onCommanderChange: (commander: Commander | null) => void
  settings: BrewSettings
  onSettingsChange: (settings: BrewSettings) => void
  onSubmit: () => void
  busy: boolean
}

const PRESETS = [25, 50, 100, 200, 500]

export function BrewForm({
  commander,
  onCommanderChange,
  settings,
  onSettingsChange,
  onSubmit,
  busy,
}: Props) {
  function update<K extends keyof BrewSettings>(key: K, value: BrewSettings[K]) {
    onSettingsChange({ ...settings, [key]: value })
  }

  return (
    <form
      className="panel"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      <CommanderSearch value={commander} onChange={onCommanderChange} />

      <div className="field">
        <label htmlFor="budget">Budget</label>
        <div className="budget-row">
          <span className="budget-prefix">$</span>
          <input
            id="budget"
            type="number"
            min={1}
            // step="any" rather than a fixed increment: with min=1, a step of
            // 5 makes 100 an INVALID value (the valid ones being 1, 6, 11...),
            // and the browser then blocks form submission silently -- no
            // event, no error, nothing happens when you click Brew.
            step="any"
            value={settings.budgetDollars}
            onChange={(e) =>
              update('budgetDollars', Math.max(1, Number(e.target.value) || 0))
            }
          />
        </div>
        <div className="presets">
          {PRESETS.map((amount) => (
            <button
              type="button"
              key={amount}
              className={settings.budgetDollars === amount ? 'preset on' : 'preset'}
              onClick={() => update('budgetDollars', amount)}
            >
              ${amount}
            </button>
          ))}
        </div>
      </div>

      <details className="advanced">
        <summary>Advanced</summary>

        <div className="field">
          <label htmlFor="lands">Land count</label>
          <input
            id="lands"
            type="number"
            min={20}
            max={48}
            value={settings.lands}
            onChange={(e) => update('lands', Number(e.target.value) || 36)}
          />
        </div>

        <label className="check">
          <input
            type="checkbox"
            checked={settings.strategy === 'tier0'}
            onChange={(e) => update('strategy', e.target.checked ? 'tier0' : 'auto')}
          />
          <span>
            Ignore commander synergy
            <span className="muted small">
              Ranks by global EDH popularity only. Produces a legal deck in the
              right colors with no identity &mdash; useful for comparison.
            </span>
          </span>
        </label>

        <label className="check">
          <input
            type="checkbox"
            checked={settings.ownedFree}
            onChange={(e) => update('ownedFree', e.target.checked)}
          />
          <span>
            Cards I own are free
            <span className="muted small">
              Budget becomes new money to spend rather than total retail value.
            </span>
          </span>
        </label>

        <label className="check">
          <input
            type="checkbox"
            checked={settings.includeUpgradePath}
            onChange={(e) => update('includeUpgradePath', e.target.checked)}
          />
          <span>
            Show upgrade path
            <span className="muted small">
              Also solves at higher budgets to show what the next money buys.
            </span>
          </span>
        </label>
      </details>

      <button type="submit" className="primary" disabled={!commander || busy}>
        {busy ? 'Brewing...' : 'Brew deck'}
      </button>
    </form>
  )
}
