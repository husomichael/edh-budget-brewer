import { dollars } from '../format'
import type { UpgradePath } from '../types'

export function UpgradePathView({ path }: { path: UpgradePath }) {
  return (
    <div className="upgrade">
      <h2>Upgrade path</h2>
      <p className="muted small">
        The same commander solved at higher budgets. Each tier shows a set of
        changes, not a single-card chain &mdash; extra money in one role can
        enable a cheaper reshuffle in another.
      </p>

      {path.best_next_buys.length > 0 && (
        <section className="next-buys">
          <h3>Best next buys</h3>
          <p className="muted small">
            Cheapest first, so you can stop partway and still have spent well.
          </p>
          <ul className="card-list">
            {path.best_next_buys.slice(0, 8).map((card) => (
              <li key={card.oracle_id} className="card-row">
                <span className="card-name">{card.name}</span>
                <span className="card-price">{dollars(card.price_cents)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <table className="tiers">
        <thead>
          <tr>
            <th>Budget</th>
            <th>Spent</th>
            <th>Score</th>
            <th>Gain</th>
            <th>$ / point</th>
            <th>Changes</th>
          </tr>
        </thead>
        <tbody>
          {path.steps.map((step) => (
            <tr key={step.label} className={step.is_no_limit ? 'no-limit' : ''}>
              <td>
                {step.label}
                {step.is_no_limit && (
                  <span className="muted small"> aspirational</span>
                )}
              </td>
              <td>{dollars(step.total_cents)}</td>
              <td>{step.score.toFixed(1)}</td>
              <td className={step.score_delta > 0 ? 'gain' : 'muted'}>
                {step.score_delta >= 0 ? '+' : ''}
                {step.score_delta.toFixed(1)}
              </td>
              <td>
                {step.cost_per_point === null
                  ? '—'
                  : `$${step.cost_per_point.toFixed(2)}`}
              </td>
              <td className="muted small">
                {step.added.length} in / {step.removed.length} out
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="caveat">
        <strong>Read these numbers with care.</strong> Score is derived from
        Scryfall's <code>edhrec_rank</code>, which is log-normalized and
        therefore compresses differences between top cards. It cannot tell that
        an expensive staple is <em>qualitatively</em> better than a cheap card
        of similar popularity, only that their ranks are close. Treat the path
        as most trustworthy under about $100, where the gains are real and
        large.
      </p>
    </div>
  )
}
