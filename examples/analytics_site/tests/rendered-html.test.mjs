import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the source-backed field notes", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(
    html,
    /<title>CFB Data Field Notes — Modular Analytics in Practice<\/title>/,
  );
  assert.match(html, /What <em>13-3<\/em>/);
  assert.match(html, /Oregon<\/span><strong>32<\/strong>/);
  assert.match(html, /Ohio State<\/span><strong>31<\/strong>/);
  assert.match(html, /Four options\. One result\./);
  assert.match(html, /pandas\/dask/);
  assert.match(html, /polars\/local/);
  assert.match(html, /655(?:<!-- -->)? → (?:<!-- -->)?655/);
  assert.match(html, /No API attempts used to generate this site/);
  assert.doesNotMatch(html, /codex-preview|Building your site|loading skeleton/i);
});

test("keeps the snapshot bounded, local, and provenance-rich", async () => {
  const [rawSnapshot, page, packageJson] = await Promise.all([
    readFile(new URL("../app/data.json", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);
  const snapshot = JSON.parse(rawSnapshot);

  assert.equal(snapshot.sourceMode, "Redis local_only");
  assert.equal(snapshot.ledgerBefore, snapshot.ledgerAfter);
  assert.equal(snapshot.runtime.plannedRecipes, 15);
  assert.equal(snapshot.runtime.parity.length, 4);
  assert.ok(snapshot.runtime.parity.every((row) => row.canonicalMatch));
  assert.deepEqual(snapshot.game.workflowOutputs, [
    "game_summaries",
    "team_games",
    "player_game_stats",
    "drives",
    "plays",
    "betting_lines",
  ]);
  assert.match(page, /team_seasons\.run/);
  assert.match(page, /program_history\.run/);
  assert.match(page, /single_game_analysis\.run/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton|drizzle/);

  await assert.rejects(
    access(
      new URL(
        "../app/_sites-preview/SkeletonPreview.tsx",
        import.meta.url,
      ),
    ),
  );
});
