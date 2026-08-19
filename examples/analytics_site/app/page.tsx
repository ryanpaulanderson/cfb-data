import snapshot from "./data.json";

const season = snapshot.season;
const game = snapshot.game;
const runtime = snapshot.runtime;
const maxDifferential = Math.max(
  ...season.schedule.map((item) => Math.abs(item.differential)),
);
const generatedAt = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
}).format(new Date(snapshot.generatedAt));

function SeasonSchedule() {
  return (
    <div
      className="schedule-chart"
      role="img"
      aria-label={`${season.team} point differential across ${season.schedule.length} games`}
    >
      {season.schedule.map((item) => (
        <div className="schedule-row" key={item.gameId}>
          <span className="week">
            {item.seasonType === "postseason" ? "P" : `W${item.week}`}
          </span>
          <span className="opponent">{item.opponent}</span>
          <div className="bar-track" aria-hidden="true">
            <div
              className={`bar ${item.differential >= 0 ? "positive" : "negative"}`}
              style={{
                width: `${Math.max(8, (Math.abs(item.differential) / maxDifferential) * 100)}%`,
              }}
            />
          </div>
          <strong className={item.differential >= 0 ? "win" : "loss"}>
            {item.differential > 0 ? "+" : ""}
            {item.differential}
          </strong>
        </div>
      ))}
    </div>
  );
}

function TeamComparison() {
  return (
    <div className="team-comparison">
      {game.teams.map((team) => (
        <article key={team.team}>
          <h3>{team.team}</h3>
          <dl>
            <div>
              <dt>Avg. PPA</dt>
              <dd>{team.averagePpa.toFixed(3)}</dd>
            </div>
            <div>
              <dt>PPA-observed plays</dt>
              <dd>{team.ppaObservedPlays}</dd>
            </div>
            <div>
              <dt>20+ yard plays</dt>
              <dd>{team.explosivePlays}</dd>
            </div>
            <div>
              <dt>Scoring drives</dt>
              <dd>{team.scoringDrives}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

function RuntimeMatrix() {
  return (
    <div className="runtime-table-wrap">
      <table className="runtime-table">
        <thead>
          <tr>
            <th>Frame / executor</th>
            <th>Canonical result</th>
            <th>Dask nodes</th>
            <th>HTTP</th>
          </tr>
        </thead>
        <tbody>
          {runtime.parity.map((row) => (
            <tr key={row.option}>
              <th scope="row">{row.option}</th>
              <td>
                <span className="match-dot" aria-hidden="true" />
                {row.canonicalMatch ? "identical" : "different"}
              </td>
              <td>{row.daskNodes}</td>
              <td>{row.httpAttempts}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Home() {
  return (
    <main id="top">
      <header className="site-header">
        <a className="wordmark" href="#top" aria-label="CFB Data field notes home">
          <span className="wordmark-mark">CD</span>
          <span>
            CFB DATA
            <small>FIELD NOTES / 001</small>
          </span>
        </a>
        <nav aria-label="Page sections">
          <a href="#season">Season</a>
          <a href="#game">Game</a>
          <a href="#runtime">Runtime</a>
        </nav>
        <div className="validation-pill">
          <span aria-hidden="true" />
          Validated local snapshot
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">PROGRAM STUDY · {season.season}</p>
          <h1>
            What <em>{season.record}</em>
            <br /> actually looked like.
          </h1>
          <p className="deck">
            A season, a one-point classic, and the execution system underneath
            them—built entirely from durable, composable recipes.
          </p>
        </div>
        <aside className="hero-aside" aria-label="Season summary">
          <p>{season.team}</p>
          <strong>{season.record}</strong>
          <span>{season.conference}</span>
          <div className="hero-rule" />
          <dl>
            <div>
              <dt>Expected wins</dt>
              <dd>{season.expectedWins}</dd>
            </div>
            <div>
              <dt>Final rank</dt>
              <dd>#{season.postseasonRank}</dd>
            </div>
          </dl>
        </aside>
      </section>

      <section className="metric-strip" aria-label="Season headline metrics">
        <article>
          <span>01</span>
          <strong>+{season.averagePointDifferential}</strong>
          <p>average scoring margin</p>
        </article>
        <article>
          <span>02</span>
          <strong>{season.awayRecord}</strong>
          <p>away from home</p>
        </article>
        <article>
          <span>03</span>
          <strong>{season.weeksTopTen}</strong>
          <p>weeks inside the top ten</p>
        </article>
        <article>
          <span>04</span>
          <strong>#{season.recruitingRank}</strong>
          <p>recruiting class</p>
        </article>
      </section>

      <section className="season-section" id="season">
        <div className="section-heading">
          <div>
            <p className="eyebrow">THE SEASON IN SIXTEEN LINES</p>
            <h2>Margin tells the shape of the year.</h2>
          </div>
          <p>
            Each bar is one validated team-game perspective. Navy moved the
            season forward; red marks the three reversals.
          </p>
        </div>
        <SeasonSchedule />
        <div className="season-notes">
          <article>
            <span>Record context</span>
            <strong>{season.conferenceRecord}</strong>
            <p>in conference, with a {season.postseasonRecord} postseason.</p>
          </article>
          <article>
            <span>Scoring ledger</span>
            <strong>{season.pointsFor}–{season.pointsAgainst}</strong>
            <p>points for and against across the complete season.</p>
          </article>
          <article>
            <span>Poll movement</span>
            <strong>#{season.preseasonRank} → #{season.postseasonRank}</strong>
            <p>with a season-best ranking of #{season.bestRank}.</p>
          </article>
        </div>
      </section>

      <section className="game-feature" id="game">
        <div className="game-score">
          <p className="eyebrow">SINGLE GAME ANALYSIS · WEEK {game.week}</p>
          <div className="scoreline">
            <div>
              <span>{game.homeTeam}</span>
              <strong>{game.homePoints}</strong>
            </div>
            <i aria-hidden="true">—</i>
            <div>
              <span>{game.awayTeam}</span>
              <strong>{game.awayPoints}</strong>
            </div>
          </div>
          <p className="game-caption">
            One point at {game.venue}. {game.playCount} source play records, {game.driveCount} drives,
            and an excitement index of {game.excitementIndex}.
          </p>
        </div>
        <div className="game-numbers">
          <div>
            <strong>{game.explosivePlayCount}</strong>
            <span>20+ yard PPA-observed plays</span>
          </div>
          <div>
            <strong>{game.scoringDriveCount}</strong>
            <span>scoring drives</span>
          </div>
          <div>
            <strong>{game.athleteCount}</strong>
            <span>athletes observed</span>
          </div>
        </div>
      </section>

      <section className="game-detail">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">THE GAME BENEATH THE SCORE</p>
            <h2>Efficiency and leverage disagreed.</h2>
          </div>
          <p>
            Ohio State led average PPA on observed plays. Oregon answered with
            more explosive plays and one more scoring drive—the slim shape of
            a one-point result.
          </p>
        </div>
        <TeamComparison />
        <div className="detail-grid">
          <article className="big-play-list">
            <div className="mini-heading">
              <span>Largest PPA-observed gains</span>
              <span>{game.ppaObservedPlayCount} records with PPA</span>
            </div>
            <ol>
              {game.bigPlays.map((play) => (
                <li key={`${play.period}-${play.text}`}>
                  <strong>{play.yards}</strong>
                  <div>
                    <span>Q{play.period} · {play.offense} · {play.type}</span>
                    <p>{play.text}</p>
                  </div>
                  <em>{play.ppa === null ? "—" : `${play.ppa > 0 ? "+" : ""}${play.ppa} PPA`}</em>
                </li>
              ))}
            </ol>
          </article>
          <article className="market-card">
            <p className="eyebrow">MARKET SNAPSHOT</p>
            <h3>Quotes preserved, not chosen.</h3>
            <p>
              The recipe keeps each provider’s quote. It does not silently
              promote one book—or relabel a value as “closing.”
            </p>
            <table>
              <thead>
                <tr><th>Provider</th><th>Spread</th><th>Total</th></tr>
              </thead>
              <tbody>
                {game.market.map((quote) => (
                  <tr key={quote.provider}>
                    <th scope="row">{quote.provider}</th>
                    <td>{quote.spread}</td>
                    <td>{quote.total ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>
        </div>
      </section>

      <section className="recruiting-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">PROGRAM HISTORY · CLASS OF {season.season}</p>
            <h2>A top-15 class, kept as people.</h2>
          </div>
          <p>
            {season.recruitCount} commitments remain ordered recruit records.
            The presentation chooses five to show; the recipe never pivots them away.
          </p>
        </div>
        <div className="recruit-grid">
          {season.topRecruits.map((recruit, index) => (
            <article key={recruit.name}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{recruit.position} · {recruit.stars}★</p>
              <h3>{recruit.name}</h3>
              <dl>
                <div><dt>National</dt><dd>#{recruit.nationalRank}</dd></div>
                <div><dt>Rating</dt><dd>{recruit.rating.toFixed(4)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>

      <section className="runtime-section" id="runtime">
        <div className="runtime-intro">
          <p className="eyebrow">THE SYSTEM UNDERNEATH</p>
          <h2>Four options. One result.</h2>
          <p>
            The same public recipes ran through pandas and Polars, locally and
            on Dask. Every canonical table matched; cache-only replay added no
            HTTP attempts.
          </p>
        </div>
        <RuntimeMatrix />
        <div className="runtime-evidence">
          <article><strong>{runtime.plannedRecipes}</strong><span>recipes planned with no I/O</span></article>
          <article><strong>{runtime.sourceCandidates}</strong><span>source candidates inspected</span></article>
          <article><strong>{runtime.actualAttempts}</strong><span>actual warm-up HTTP attempts</span></article>
          <article><strong>{runtime.checkpointDaskStarts}</strong><span>Dask starts on checkpoint replay</span></article>
        </div>
        <div className="recipe-proof">
          <div>
            <span>01 / DATASET</span>
            <code>team_seasons.run(...)</code>
            <p>One validated team-season row establishes the headline record.</p>
          </div>
          <div>
            <span>02 / WORKFLOW</span>
            <code>program_history.run(...)</code>
            <p>Games, coaches, polls, and recruiting remain named outputs.</p>
          </div>
          <div>
            <span>03 / WORKFLOW</span>
            <code>single_game_analysis.run(...)</code>
            <p>{game.workflowOutputs.length} independently validated outputs compose the game story.</p>
          </div>
        </div>
      </section>

      <footer>
        <div>
          <strong>CFB DATA / FIELD NOTES</strong>
          <p>Generated {generatedAt} UTC from {snapshot.sourceMode}.</p>
        </div>
        <div className="ledger-proof">
          <span>API ledger</span>
          <strong>{snapshot.ledgerBefore} → {snapshot.ledgerAfter}</strong>
          <p>No API attempts used to generate this site.</p>
        </div>
      </footer>
    </main>
  );
}
