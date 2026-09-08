// Build a shareable report for a candidate harness: REPORT.md plus a self-contained
// index.html with the chart inlined.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const SOURCE_EVAL = "https://frontierharness.org/";

const args = parseArgs(process.argv.slice(2));
const runDir = args.run ?? die("usage: build-report.mjs --run runs/<run-id> [--baseline results/eval-data.json]");
const baselinePath = args.baseline ?? "results/eval-data.json";

const labels = {
  "pi-responses": "Pi", "oh-my-pi": "Oh My Pi", "claude-code": "Claude Code", codex: "Codex",
  opencode: "OpenCode", hermes: "Hermes", "kimi-code": "Kimi Code", exo: "Exo Harness",
  "dsh-standard": "DSH Standard", "dsh-ptc": "DSH PTC", "dsh-minimal": "DSH Minimal",
  "dsh-creator": "DSH Creator",
};

const baseline = await readJson(baselinePath, `baseline not found at ${baselinePath}; pass --baseline <path to eval-data.json>`);
const candidate = await readJson(join(runDir, "candidate.json"), `candidate.json not found in ${runDir}; run normalize-results.mjs first`);
const run = await readJson(join(runDir, "run.json"), `run.json not found in ${runDir}`);
const comparable = candidate.comparable === true;
const manifest = await readJsonOrNull(join(runDir, "trials", firstTrialDir(candidate), "manifest.json"));

const reportDir = join(runDir, "report");
await mkdir(reportDir, { recursive: true });
const chart = await readFile(join(reportDir, "chart.svg"), "utf8").catch(() => null);
if (!chart) die("chart.svg not found; run generate-chart.mjs first");

const rows = [
  ...baseline.harnesses.map(item => ({
    label: labels[item.name] ?? item.name,
    passRate: item.pass_rate,
    cost: item.effective_cost_per_pass,
    cache: item.cache_hit_rate_typical,
    duration: item.median_duration_seconds,
    isCandidate: false,
  })),
  {
    label: candidate.label,
    passRate: candidate.pass_rate,
    cost: candidate.effective_cost_per_pass,
    cache: candidate.cache_hit_rate_typical,
    duration: candidate.median_duration_seconds,
    isCandidate: true,
  },
].sort((a, b) => b.passRate - a.passRate || a.label.localeCompare(b.label));

const rank = rows.findIndex(row => row.isCandidate) + 1;
if (!comparable) rows.sort((a, b) => Number(a.isCandidate) - Number(b.isCandidate) || b.passRate - a.passRate || a.label.localeCompare(b.label));
const rankingClause = comparable ? `ranking **${rank} of ${rows.length}** on pass rate against the published configurations` : `**${candidate.completed < candidate.expected ? 'subset evaluation' : 'methodology differs'}; not ranked against the ${candidate.expected}-task leaderboard**`;
const percent = value => typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "n/a";
const money = value => typeof value === "number" ? `$${value.toFixed(2)}` : "n/a";
const duration = value => {
  if (typeof value !== "number") return "n/a";
  const seconds = Math.round(value);
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
};

// A partial observed median is diagnostic; never replace the canonical aggregate.
const cacheTasks = candidate.task_details.filter(task => task.status === "success" && task.success);
const observedCacheRates = cacheTasks.map(task => task.cache_hit_rate_normalized)
  .filter(value => Number.isFinite(value) && value >= 0 && value <= 1).sort((a, b) => a - b);
const observedCacheMedian = observedCacheRates.length
  ? (observedCacheRates[Math.floor((observedCacheRates.length - 1) / 2)] + observedCacheRates[Math.floor(observedCacheRates.length / 2)]) / 2
  : null;
const completeCache = Number.isFinite(candidate.cache_hit_rate_typical);
const cacheValue = completeCache ? candidate.cache_hit_rate_typical : observedCacheMedian;
const cachePartial = !completeCache && cacheValue !== null;
const cacheCount = completeCache ? (candidate.cache_hit_rate_typical_n ?? candidate.successful) : observedCacheRates.length;
const cacheCoverageText = `${cacheCount}/${candidate.successful} successful tasks with measured cache rates`;
const cacheDisplay = cacheValue === null ? "Unavailable" : `${percent(cacheValue)}${cachePartial ? " (partial)" : ""}`;
const missingCacheTasks = cacheTasks.filter(task => !Number.isFinite(task.cache_hit_rate_normalized)).map(task => task.id);
const cacheExplanation = `${cacheCoverageText}. Rates exclude first-call cached tokens. ${cachePartial
  ? "The displayed median covers observed successes only; the full-success aggregate remains unavailable."
  : cacheValue === null ? "No complete cache measurements are available; missing usage is not zero cache hits." : "The median covers all successful tasks."}${missingCacheTasks.length ? ` Missing complete cache usage: ${missingCacheTasks.join(", ")}.` : ""}`;

const comparison = rows.map((row, index) => {
  const name = row.isCandidate ? `**${row.label}**` : row.label;
  return `| ${row.isCandidate && !comparable ? '—' : String(index + 1).padStart(2, "0")} | ${name} | ${percent(row.passRate)} | ${money(row.cost)} | ${row.isCandidate ? cacheDisplay : percent(row.cache)} | ${duration(row.duration)} |`;
}).join("\n");

// Require a scored failure from every baseline; missing/invalid cells are not failures.
const exclusiveSolves = new Set(candidate.task_details.filter(task =>
  task.status === "success" && task.success === true && baseline.harnesses.length > 0
  && baseline.harnesses.every(harness => {
    const cells = (harness.task_details ?? []).filter(cell => cell.id === task.id);
    return cells.length === 1 && cells[0].status === "failure" && cells[0].success === false;
  })
).map(task => task.id));
const exclusiveBadge = `★ Solved · 0/${baseline.harnesses.length} baselines passed`;
const exclusiveNote = exclusiveSolves.size
  ? `★ Highlighted tasks were solved by this harness while every published baseline configuration recorded a failure on the same task. Times are this harness's full runner wall time.${comparable ? "" : " These are observed results from an unranked run; evaluation conditions are not established as equivalent."}`
  : "";

const taskRows = candidate.task_details.map(task => {
  const highlighted = exclusiveSolves.has(task.id);
  const mark = highlighted ? exclusiveBadge : task.status === "success" ? "pass" : task.status === "infra_invalid" ? "invalid" : task.status;
  return `| \`${task.id}\` | ${mark} | ${money(task.cost_first_cold_usd)} | ${highlighted ? `**${duration(task.duration_seconds)}**` : duration(task.duration_seconds)} | ${task.turns ?? "n/a"} | ${percent(task.cache_hit_rate_normalized)} | [evidence](../${task.evidence}) |`;
}).join("\n");

const hasCost = typeof candidate.effective_cost_per_pass === "number";
const costClause = hasCost ? ` at **${money(candidate.effective_cost_per_pass)} per pass**` : "";

const markdown = `# ${candidate.label} on FrontierHarness Eval

**${percent(candidate.pass_rate)} pass rate** (${candidate.successful}/${candidate.completed} tasks)${costClause}; ${rankingClause}.

![Pass rate versus effective cost per pass, ${candidate.label} against the FrontierHarness Eval baselines](chart.svg)

## Result

| Metric | Value |
| --- | --- |
| Pass rate | ${percent(candidate.pass_rate)} |
| Tasks passed | ${candidate.successful} / ${candidate.completed} |
| Effective cost per pass | ${money(candidate.effective_cost_per_pass)} |
| Median cost per successful task | ${money(candidate.median_cost_per_success)} |
| Median time per successful task | ${duration(candidate.median_duration_seconds)} |
| Median cache hit rate | ${cacheDisplay} |
| Cache measurement coverage | ${cacheCoverageText} |
| Mean turns | ${typeof candidate.mean_turns === "number" ? candidate.mean_turns.toFixed(1) : "n/a"} |

${cacheExplanation}

## Comparison

| # | Harness | Pass rate | Effective cost per pass | Cache, median | Median time |
| --- | --- | --- | --- | --- | --- |
${comparison}

## Reproducibility

| Field | Value |
| --- | --- |
| Run id | \`${run.run_id}\` |
| Golden checkpoint | \`${run.checkpoint}\` |
| Model | \`${candidate.model ?? "unspecified"}\` |
| Provider | ${candidate.provider ? `\`${candidate.provider}\`` : "unspecified"} |
| Harness repo | ${manifest?.harness_repo ? `\`${manifest.harness_repo}\`` : "see manifest"} |
| Harness commit | \`${manifest?.harness_commit ?? "unknown"}\`${manifest?.harness_commit_role ? ` (${manifest.harness_commit_role})` : ""} |
${manifest?.harness_release ? `| Evaluated release | ${manifest.harness_release} (${manifest.harness_distribution}) |\n` : ""}\
| Runtime | ${manifest ? `${manifest.cpus} vCPU, ${manifest.memory_mib} MiB` : "see manifest"} |
| Harbor | \`${manifest?.harbor_version ?? "unknown"}\` |
| Pier | \`${manifest?.pier_version ?? "unknown"}\` |
| DeepSWE corpus | \`${manifest?.deep_swe_commit ?? "unknown"}\` |
| Started | ${run.started_at ?? "unknown"} |

Every trial restores the same base checkpoint with the same configured vCPU, memory, and disk capacity. Task images are normally pulled after restore. No formal task was executed before the checkpoint was frozen.

## Task results

${exclusiveNote}

| Task | Result | Cost | Time | Turns | Cache hit rate | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
${taskRows}

Each evidence directory holds the agent trajectory, verifier logs, the collected \`model.patch\`, and raw runner output for that trial.

---

Baseline data and methodology: [FrontierHarness Eval](${SOURCE_EVAL})
`;

await writeFile(join(reportDir, "REPORT.md"), markdown);

const html = `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>${escapeHtml(candidate.label)} on FrontierHarness Eval</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: dark; --bg: #000; --text: #ededed; --muted: #929292; --line: #282828; --accent: #f47b35; }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; scroll-padding-top: 72px; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }
  main { max-width: 1160px; margin: auto; padding: 28px 24px 48px; }
  .brand { display: flex; align-items: center; gap: 16px; margin-bottom: 40px; color: var(--accent); font-weight: 650; letter-spacing: .02em; }
  .brand span, .eyebrow { font: 11px/1.5 "SFMono-Regular", Consolas, monospace; color: var(--muted); }
  .brand span { border: 1px solid var(--line); padding: 4px 9px; }
  h1 { font-size: clamp(28px, 4vw, 44px); line-height: 1.15; font-weight: 550; letter-spacing: -.035em; margin: 8px 0 18px; overflow-wrap: anywhere; }
  h2 { font-size: 20px; margin: 0 0 20px; font-weight: 500; letter-spacing: -.02em; }
  p.lede { color: var(--muted); max-width: 850px; margin: 0 0 30px; overflow-wrap: anywhere; }
  strong { color: var(--text); font-weight: 550; }
  .chart { margin: 24px -24px; overflow-x: auto; }
  svg { width: 100%; min-width: 760px; height: auto; display: block; }
  nav { display: flex; gap: 26px; padding: 16px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); overflow-x: auto; }
  nav a { color: var(--muted); white-space: nowrap; font-size: 13px; }
  .metrics { display: grid; grid-template-columns: repeat(4, 1fr); margin: 32px 0 48px; }
  .metric { padding: 0 20px; border-left: 1px solid var(--line); }
  .metric:first-child { padding-left: 0; border: 0; }
  .metric span { display: block; color: var(--muted); font: 11px/1.5 "SFMono-Regular", Consolas, monospace; }
  .metric strong { display: block; font-size: 28px; margin: 5px 0; font-variant-numeric: tabular-nums; }
  section { margin-top: 48px; scroll-margin-top: 24px; }
  .table-scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
  th, td { text-align: left; padding: 13px 12px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font: 11px/1.5 "SFMono-Regular", Consolas, monospace; white-space: nowrap; }
  td:not(:nth-child(2)), code { font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }
  tr.candidate { background: #f47b350d; }
  tr.candidate td { color: var(--accent); }
  tr.exclusive-solve { background: #ff7a1214; }
  tr.exclusive-solve td { border-bottom-color: #ff7a1240; }
  tr.exclusive-solve td:first-child { border-left: 3px solid var(--accent); }
  .solve-badge, tr.exclusive-solve .solve-time { color: var(--accent); font-weight: 650; }
  tbody tr:hover { background: #ffffff06; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  a:focus-visible { outline: 2px solid var(--accent); outline-offset: 5px; }
  footer { margin-top: 64px; padding-top: 24px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
  @media (max-width: 640px) { main { padding: 20px 16px 32px; } .brand { margin-bottom: 28px; } .chart { margin-inline: -16px; } .metrics { grid-template-columns: repeat(2, 1fr); gap: 24px 0; } .metric:nth-child(3) { padding-left: 0; border: 0; } nav { gap: 20px; } th, td { padding: 10px; } }
  @media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
</style>
<main>
  <div class="brand">FrontierHarness Eval <span>HARNESS REPORT</span></div>
  <div class="eyebrow">CANDIDATE EVALUATION</div>
  <h1>${escapeHtml(candidate.label)} on FrontierHarness Eval</h1>
  <p class="lede"><strong>${percent(candidate.pass_rate)}</strong> pass rate (${candidate.successful}/${candidate.completed} tasks)${hasCost ? `
     at <strong>${money(candidate.effective_cost_per_pass)}</strong> per pass` : ""}; ${comparable ? `ranking ${rank} of ${rows.length}` : `${candidate.completed < candidate.expected ? "subset evaluation" : "methodology differs"}; not ranked against the ${candidate.expected}-task leaderboard`}.
     Model <code>${escapeHtml(candidate.model ?? "unspecified")}</code>,
     golden checkpoint <code>${escapeHtml(run.checkpoint)}</code>.</p>
  <div class="chart">${chart.replace(/^<\?xml[^>]*\?>\s*/, "")}
  </div>
  <nav aria-label="Report sections"><a href="#result">Result</a><a href="#comparison">Comparison</a><a href="#tasks">Task results</a></nav>
  <div class="metrics" id="result">
    <div class="metric"><span>Pass rate</span><strong>${percent(candidate.pass_rate)}</strong><span>${candidate.successful} / ${candidate.completed} scored tasks</span></div>
    <div class="metric"><span>Effective cost per pass</span><strong>${money(candidate.effective_cost_per_pass)}</strong><span>Includes known costs of failures</span></div>
    <div class="metric"><span>Median successful runtime</span><strong>${duration(candidate.median_duration_seconds)}</strong><span>Full runner wall time</span></div>
    <div class="metric"><span>Median cache hit rate</span><strong>${cacheValue === null ? "Unavailable" : percent(cacheValue)}</strong><span>${cachePartial ? "Partial · " : ""}${cacheCount}/${candidate.successful} successes measured</span></div>
  </div>
  <p class="lede">${escapeHtml(cacheExplanation)}</p>
  <section id="comparison"><h2>Comparison</h2>
  <div class="table-scroll">
  <table>
    <tr><th>#</th><th>Harness</th><th>Pass rate</th><th>Effective cost per pass</th><th>Cache, median</th><th>Median time</th></tr>
    ${rows.map((row, index) => `<tr${row.isCandidate ? ' class="candidate"' : ""}><td>${row.isCandidate && !comparable ? '—' : index + 1}</td><td>${escapeHtml(row.label)}</td><td>${percent(row.passRate)}</td><td>${money(row.cost)}</td><td>${row.isCandidate ? cacheDisplay : percent(row.cache)}</td><td>${duration(row.duration)}</td></tr>`).join("\n    ")}
  </table>
  </div></section>
  <section id="tasks"><h2>Task results</h2>
  ${exclusiveNote ? `<p class="lede">${escapeHtml(exclusiveNote)}</p>` : ""}
  <div class="table-scroll">
  <table>
    <tr><th>Task</th><th>Result</th><th>Cost</th><th>Time</th><th>Turns</th><th>Cache hit rate</th></tr>
    ${candidate.task_details.map(task => `<tr${exclusiveSolves.has(task.id) ? ' class="exclusive-solve"' : ""}><td><code>${escapeHtml(task.id)}</code></td><td>${exclusiveSolves.has(task.id) ? `<span class="solve-badge">${exclusiveBadge}</span>` : task.status}</td><td>${money(task.cost_first_cold_usd)}</td><td class="solve-time">${duration(task.duration_seconds)}</td><td>${task.turns ?? "n/a"}</td><td>${percent(task.cache_hit_rate_normalized)}</td></tr>`).join("\n    ")}
  </table>
  </div></section>
  <footer>Baseline data and methodology: <a href="${SOURCE_EVAL}">FrontierHarness Eval</a></footer>
</main>
</html>
`;

await writeFile(join(reportDir, "index.html"), html);

console.log(`${candidate.label}: ${percent(candidate.pass_rate)} pass rate, ${comparable ? `rank ${rank} of ${rows.length}` : 'candidate not ranked'}`);
console.log(`wrote ${join(reportDir, "REPORT.md")}`);
console.log(`wrote ${join(reportDir, "index.html")}`);
console.log(`share: gh gist create ${join(reportDir, "REPORT.md")} ${join(reportDir, "chart.svg")} --public`);

function firstTrialDir(record) {
  const withEvidence = record.task_details.find(task => task.evidence);
  return withEvidence ? withEvidence.evidence.replace(/^trials\//, "") : "";
}

async function readJsonOrNull(path) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch {
    return null;
  }
}

async function readJson(path, message) {
  const parsed = await readJsonOrNull(path);
  return parsed ?? die(message);
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function parseArgs(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index].startsWith("--")) parsed[argv[index].slice(2)] = argv[index + 1];
  }
  return parsed;
}

function die(message) {
  console.error(message);
  process.exit(2);
}
