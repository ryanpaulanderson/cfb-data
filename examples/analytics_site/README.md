# CFB Data Analytics Field Notes

This local-only editorial site turns real recipe outputs into a readable season
and game study. It is an example consumer of the public analytics API, not a
privileged dashboard implementation.

The committed snapshot was built from:

- `team_seasons.run(...)` for Penn State's 2024 record;
- `program_history.run(...)` for schedule, poll, coach, and recruiting context;
- `single_game_analysis.run(...)` for Oregon–Ohio State game, play, drive,
  player-stat, and market evidence; and
- the redacted four-way pandas/Polars × local/Dask live-acceptance report.

The snapshot generator uses Redis `local_only` mode and refuses to write output
if the cumulative live-call ledger changes. Site generation therefore cannot
silently spend an API attempt.

## View the committed snapshot

From this directory:

```bash
npm install
npm run dev
```

Open the local URL printed by the development server. No API key, Redis server,
or network access is needed to render the committed snapshot.

## Regenerate from the persistent Redis cache

Install the repository development environment and start the existing Redis
service. Set `CFBD_API_KEY` to the credential whose scope populated
`cfb-data:penn-state-atlas`, then run from the repository root:

```bash
make redis-up
.venv/bin/python examples/analytics_site/scripts/generate_snapshot.py
```

The script requires the passing ignored live report at
`.cfb-data-live/live-analytics-report.json`. It uses an isolated temporary
analytics artifact root and atomically replaces `app/data.json` only after all
recipes complete and the API ledger remains unchanged.

## Analytical choices

Retrieval data is not changed. Reader-facing summaries are deliberately made in
the example's analytical presentation layer:

- point differential is shown only from validated team-game perspectives;
- game efficiency uses records with non-null source PPA, so administrative play
  rows carrying yard-like source values do not inflate offensive totals;
- an explosive play is a PPA-observed play with at least 20 source yards;
- betting quotes remain provider-specific, with no preferred book or invented
  closing-line label; and
- the recruiting recipe preserves all ordered recruit records while the page
  explicitly displays only the first five.

## Verify the site

```bash
npm run lint
npm test
```

`npm test` creates a production build and checks the rendered HTML, snapshot
provenance, and removal of starter-only behavior. Runtime dependencies have no
known npm audit findings at the time of validation; development-only build
tooling is audited and reported separately in the pull request evidence.
