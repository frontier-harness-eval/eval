import { websiteCost as calculateWebsiteCost } from "./website-cost.mjs";
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
const observedAudit = await readJsonOrNull(join(runDir, "observed-cost-audit.json"));
const observedNote = observedAudit && Number.isFinite(observedAudit.observed_cost_usd)
  ? `Recorded model cost across ${observedAudit.tasks?.length ?? candidate.expected} canonical tasks: $${observedAudit.observed_cost_usd.toFixed(2)} at frozen benchmark token prices. Usage recorded for ${observedAudit.usage_calls}/${observedAudit.requests} requests; ${observedAudit.missing_usage} requests lack usage, so this is a lower bound. This diagnostic total uses observed tokens without first-call cold adjustment, excludes earlier attempts and runtime charges, and is not actual provider billing. For the website-aligned aggregate, complete first-cold task costs take precedence; available observed costs fill otherwise missing task totals without double counting. Missing usage and any unmeasured first-call adjustment remain unknown.` : "";
const comparable = candidate.comparable === true;
const displayRank = comparable || args["display-rank"] === "true";
const manifest = await readJsonOrNull(join(runDir, "trials", firstTrialDir(candidate), "manifest.json"));

const reportDir = join(runDir, "report");
await mkdir(reportDir, { recursive: true });
const chart = await readFile(join(reportDir, "chart.svg"), "utf8").catch(() => null);
if (!chart) die("chart.svg not found; run generate-chart.mjs first");

const rows = [
  ...baseline.harnesses.map(item => ({
    label: labels[item.name] ?? item.name,
    passRate: item.pass_rate,
    cost: websiteCost(item),
    cache: item.cache_hit_rate_typical,
    duration: item.median_duration_seconds,
    isCandidate: false,
  })),
  {
    label: candidate.label,
    passRate: candidate.pass_rate,
    cost: websiteCost(candidate),
    cache: candidate.cache_hit_rate_typical,
    duration: candidate.median_duration_seconds,
    isCandidate: true,
  },
].sort((a, b) => b.passRate - a.passRate || a.label.localeCompare(b.label));

const rank = rows.findIndex(row => row.isCandidate) + 1;
if (!displayRank) rows.sort((a, b) => Number(a.isCandidate) - Number(b.isCandidate) || b.passRate - a.passRate || a.label.localeCompare(b.label));
const rankingClause = displayRank ? `${comparable ? "ranking" : "provisional display rank"} **${rank} of ${rows.length}** on pass rate${comparable ? "" : "; evaluation conditions differ; not an official leaderboard rank"}` : `**${candidate.completed < candidate.expected ? 'subset evaluation' : 'methodology differs'}; not ranked against the ${candidate.expected}-task leaderboard**`;
const percent = value => typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "Not recorded";
const money = value => typeof value === "number" ? `$${value.toFixed(2)}` : "Not recorded";
const duration = value => {
  if (typeof value !== "number") return "Not recorded";
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
const cacheDisplay = cacheValue === null ? "Unavailable" : `${percent(cacheValue)}`;
const missingCacheTasks = cacheTasks.filter(task => !Number.isFinite(task.cache_hit_rate_normalized)).map(task => task.id);
const cacheExplanation = `${cacheCoverageText}. Rates exclude first-call cached tokens. ${cachePartial
  ? "The displayed median covers observed successes only; the full-success aggregate remains unavailable."
  : cacheValue === null ? "No complete cache measurements are available; missing usage is not zero cache hits." : "The median covers all successful tasks."}${missingCacheTasks.length ? ` Missing complete cache usage: ${missingCacheTasks.join(", ")}.` : ""}`;

const comparison = rows.map((row, index) => {
  const name = row.isCandidate ? `**${row.label}**` : row.label;
  return `| ${row.isCandidate && !displayRank ? '—' : String(index + 1).padStart(2, "0")} | ${name} | ${percent(row.passRate)} | ${money(row.cost)} | ${row.isCandidate ? cacheDisplay : percent(row.cache)} | ${duration(row.duration)} |`;
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

const observedByTask = new Map((observedAudit?.tasks ?? []).map(t => [t.task, t]));
const taskCostDisplay = task => {
  if (Number.isFinite(task.cost_first_cold_usd)) return money(task.cost_first_cold_usd);
  const observed = observedByTask.get(task.id);
  return Number.isFinite(observed?.observed_cost_usd)
    ? money(observed.observed_cost_usd) : "Usage not recorded";
};
const taskCacheDisplay = task => {
  if (Number.isFinite(task.cache_hit_rate_normalized)) return percent(task.cache_hit_rate_normalized);
  const observed = observedByTask.get(task.id);
  return Number.isFinite(observed?.observed_raw_cache_rate)
    ? percent(observed.observed_raw_cache_rate) : "Cache usage not recorded";
};
const measuredSuccessCosts = cacheTasks.map(t => t.cost_first_cold_usd).filter(Number.isFinite).sort((a,b) => a-b);
const successfulCostValue = Number.isFinite(candidate.median_cost_per_success) ? candidate.median_cost_per_success
  : measuredSuccessCosts.length ? (measuredSuccessCosts[Math.floor((measuredSuccessCosts.length-1)/2)] + measuredSuccessCosts[Math.floor(measuredSuccessCosts.length/2)])/2 : null;
const successfulCostDisplay = successfulCostValue === null ? "Usage not recorded" : `${money(successfulCostValue)} (${measuredSuccessCosts.length}/${candidate.successful} successes measured)`;
const diagnosticNote = "Costs for tasks with incomplete usage are observed lower bounds, shown as plain dollar values. Cache percentages for tasks with incomplete usage use cached/input tokens from available calls, including first-call cache reads. These differ from the normalized rates used in summary metrics; per-task call coverage is retained in observed-cost-audit.json. The website-aligned aggregate includes these bounds once, using complete task costs wherever available.";

const taskRows = candidate.task_details.map(task => {
  const highlighted = exclusiveSolves.has(task.id);
  const mark = highlighted ? exclusiveBadge : task.status === "success" ? "pass" : task.status === "infra_invalid" ? "invalid" : task.status;
  return `| \`${task.id}\` | ${mark} | ${taskCostDisplay(task)} | ${highlighted ? `**${duration(task.duration_seconds)}**` : duration(task.duration_seconds)} | ${task.turns ?? "Not recorded"} | ${taskCacheDisplay(task)} | [evidence](../${task.evidence}) |`;
}).join("\n");

const costMeasured = candidate.task_details.filter(t => Number.isFinite(t.cost_first_cold_usd)).length;
const costCoverageNote = `Complete cost coverage: ${costMeasured}/${candidate.expected} tasks. Website-aligned metric for every harness: total available task costs divided by passes, including failures. For incomplete tasks, include observed usage costs as lower bounds rather than discard the entire task. The public label “Median cost per task” is retained to match frontierharness.org; this is not a statistical median. Missing costs are excluded, never zero-filled.`;
const hasCost = typeof websiteCost(candidate) === "number";
const costClause = hasCost ? ` at **${money(websiteCost(candidate))} median cost per task**` : "";

const markdown = `# ${candidate.label} on FrontierHarness Eval

**${percent(candidate.pass_rate)} pass rate** (${candidate.successful}/${candidate.completed} tasks)${costClause}; ${rankingClause}.

![Pass rate versus median cost per task, ${candidate.label} against the FrontierHarness Eval baselines](chart.svg)

## Result

| Metric | Value |
| --- | --- |
| Pass rate | ${percent(candidate.pass_rate)} |
| Tasks passed | ${candidate.successful} / ${candidate.completed} |
| Cost per pass | ${money(websiteCost(candidate))} |
| Median cost per successful task | ${successfulCostDisplay} |
| Median time per successful task | ${duration(candidate.median_duration_seconds)} |
| Median cache hit rate | ${cacheDisplay} |
| Cache measurement coverage | ${cacheCoverageText} |
| Mean turns | ${typeof candidate.mean_turns === "number" ? candidate.mean_turns.toFixed(1) : "Not recorded"} |

${cacheExplanation}

${costCoverageNote}

${observedNote}

## Comparison

| # | Harness | Pass rate | Median cost per task | Cache, median | Median time |
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

${run.checkpoint === "none" ? "Checkpoint creation and restoration were skipped. Runtimes were reused across tasks; evaluation conditions differ from the published baselines. Detailed provenance is retained in candidate.json." : "Every trial restores the same base checkpoint with the same configured vCPU, memory, and disk capacity. Task images are normally pulled after restore. No formal task was executed before the checkpoint was frozen."}

## Task results

${diagnosticNote}

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
     at <strong>${money(websiteCost(candidate))}</strong> median cost per task` : ""}; ${displayRank ? `${comparable ? "ranking" : "provisional display rank"} ${rank} of ${rows.length}${comparable ? "" : "; evaluation conditions differ"}` : `${candidate.completed < candidate.expected ? "subset evaluation" : "methodology differs"}; not ranked against the ${candidate.expected}-task leaderboard`}.
     Model <code>${escapeHtml(candidate.model ?? "unspecified")}</code>,
     golden checkpoint <code>${escapeHtml(run.checkpoint)}</code>.</p>
  <div class="chart">${chart.replace(/^<\?xml[^>]*\?>\s*/, "")}
  </div>
  <nav aria-label="Report sections"><a href="#result">Result</a><a href="#comparison">Comparison</a><a href="#tasks">Task results</a></nav>
  <div class="metrics" id="result">
    <div class="metric"><span>Pass rate</span><strong>${percent(candidate.pass_rate)}</strong><span>${candidate.successful} / ${candidate.completed} scored tasks</span></div>
    <div class="metric"><span>Cost per pass</span><strong>${money(websiteCost(candidate))}</strong><span>${money(websiteCost(candidate) === null ? null : websiteCost(candidate) * candidate.successful)} total / ${candidate.successful} passes</span></div>
    <div class="metric"><span>Median successful runtime</span><strong>${duration(candidate.median_duration_seconds)}</strong><span>Full runner wall time</span></div>
    <div class="metric"><span>Median cache hit rate</span><strong>${cacheValue === null ? "Unavailable" : percent(cacheValue)}</strong><span>${cacheCount}/${candidate.successful} successes measured</span></div>
  </div>
  <p class="lede">${escapeHtml(cacheExplanation)}</p><p class="lede">${escapeHtml(costCoverageNote)}</p>${observedNote ? `<p class="lede">${escapeHtml(observedNote)}</p>` : ""}
  <section id="comparison"><h2>Comparison</h2>
  <div class="table-scroll">
  <table>
    <tr><th>#</th><th>Harness</th><th>Pass rate</th><th>Median cost per task</th><th>Cache, median</th><th>Median time</th></tr>
    ${rows.map((row, index) => `<tr${row.isCandidate ? ' class="candidate"' : ""}><td>${row.isCandidate && !displayRank ? '—' : index + 1}</td><td>${escapeHtml(row.label)}</td><td>${percent(row.passRate)}</td><td>${money(row.cost)}</td><td>${row.isCandidate ? cacheDisplay : percent(row.cache)}</td><td>${duration(row.duration)}</td></tr>`).join("\n    ")}
  </table>
  </div></section>
  <section id="tasks"><h2>Task results</h2><p class="lede">${escapeHtml(diagnosticNote)}</p>
  ${exclusiveNote ? `<p class="lede">${escapeHtml(exclusiveNote)}</p>` : ""}
  <div class="table-scroll">
  <table>
    <tr><th>Task</th><th>Result</th><th>Cost</th><th>Time</th><th>Turns</th><th>Cache hit rate</th></tr>
    ${candidate.task_details.map(task => `<tr${exclusiveSolves.has(task.id) ? ' class="exclusive-solve"' : ""}><td><code>${escapeHtml(task.id)}</code></td><td>${exclusiveSolves.has(task.id) ? `<span class="solve-badge">${exclusiveBadge}</span>` : task.status}</td><td>${taskCostDisplay(task)}</td><td class="solve-time">${duration(task.duration_seconds)}</td><td>${task.turns ?? "Not recorded"}</td><td>${taskCacheDisplay(task)}</td></tr>`).join("\n    ")}
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

// Website chart compatibility: the public label differs from the accounting field.
function websiteCost(record) {
  return calculateWebsiteCost(record, record === candidate ? observedAudit : null);
}
