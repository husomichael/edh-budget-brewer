/**
 * Attribution and legal (#27, #28).
 *
 * Scryfall's terms require attribution and forbid implying endorsement, and
 * the Wizards Fan Content Policy requires the notice below. Both were
 * previously only in the README, which is not where a visitor looks.
 */
export function Footer({ demoMode }: { demoMode: boolean }) {
  return (
    <footer className="app-footer">
      <p>
        Card data and prices from{' '}
        <a href="https://scryfall.com" target="_blank" rel="noreferrer noopener">
          Scryfall
        </a>
        . Prices are sourced from TCGplayer and Cardmarket, refreshed nightly,
        and <strong>indicative only</strong> &mdash; your local market will
        differ. Scryfall is not affiliated with this project and does not
        endorse it.
      </p>

      <p>
        {demoMode ? (
          <>
            This hosted demo is <strong>read-only</strong>: no accounts, and
            nothing you do here is saved. Collection tracking and saved decks
            live in the{' '}
            <a
              href="https://github.com/husomichael/edh-budget-brewer-cli"
              target="_blank"
              rel="noreferrer noopener"
            >
              command-line version
            </a>
            , where per-user state actually makes sense.
          </>
        ) : (
          <>
            Running locally, so saved decks and collection tracking are
            available. There is also a{' '}
            <a
              href="https://github.com/husomichael/edh-budget-brewer-cli"
              target="_blank"
              rel="noreferrer noopener"
            >
              command-line version
            </a>
            .
          </>
        )}{' '}
        Source:{' '}
        <a
          href="https://github.com/husomichael/edh-budget-brewer"
          target="_blank"
          rel="noreferrer noopener"
        >
          edh-budget-brewer
        </a>
        .
      </p>

      <p className="legal">
        A personal, non-commercial project. Unofficial Fan Content permitted
        under the Wizards of the Coast Fan Content Policy. Not approved or
        endorsed by Wizards. Portions of the materials used are property of
        Wizards of the Coast LLC. Magic: The Gathering is a trademark of
        Wizards of the Coast.
      </p>
    </footer>
  )
}
