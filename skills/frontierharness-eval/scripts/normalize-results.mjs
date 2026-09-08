// Fold per-task trial.json files into a candidate harness record that uses the same
// field names and definitions as results/eval-data.json.
import { readdir, readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { join } from "node:path";

const args = parseArgs(process.argv.slice(2));
const runDir = args.run ?? die("usage: normalize-results.mjs --run runs/<run-id> [--label \"My Harness\"] [--name my-harness]");

let run;
try {
  run = JSON.parse(await readFile(join(runDir, "run.json"), "utf8"));
} catch {
  die(`run.json not found in ${runDir}; run run-trials.sh first`);
}

const trialsDir = join(runDir, "trials");
const entries = (await readdir(trialsDir, { withFileTypes: true }).catch(() => die(`no trials directory in ${runDir}`)))
  .filter(entry => entry.isDirectory());

let trials = [];
for (const entry of entries) {
  const path = join(trialsDir, entry.name, "trial.json");
  try {
    trials.push({ ...JSON.parse(await readFile(path, "utf8")), evidence: join("trials", entry.name) });
  } catch {
    console.warn(`skipping ${entry.name}: no readable trial.json`);
  }
}
if (!trials.length) die(`no trials found in ${trialsDir}`);

// Recalculate from retained evidence too, so existing runs can be corrected without
// rerunning the model or changing their raw trial records.
for (const trial of trials) {
  const trialDir = join(runDir, trial.evidence);
  if (trial.recovery || !existsSync(join(trialDir, "jobs"))) continue;
  const accounting = JSON.parse(execFileSync("python3", [
    fileURLToPath(new URL("./calculate-cost.py", import.meta.url)),
    "--score", "--trial", trialDir, "--model", run.model ?? "", "--harness", run.harness ?? "",
    ...(args.pricing ? ["--pricing", args.pricing] : []),
  ], { encoding: "utf8" }));
  Object.assign(trial, accounting);
}

// Restrict the population to the frozen manifest before selecting canonical cells.
const benchmark = JSON.parse(await readFile(args.benchmark ?? 'benchmark.json', 'utf8'));
const taskIds = benchmark.task_ids;
if (!Number.isInteger(benchmark.task_count) || benchmark.task_count <= 0 || !Array.isArray(taskIds) || taskIds.length !== benchmark.task_count || new Set(taskIds).size !== benchmark.task_count)
  die("benchmark.json must provide unique task_ids matching task_count");
const expected = taskIds.length;
const grouped = new Map();
for (const trial of trials) {
  const label = String(trial.label ?? run.label ?? "").toLowerCase();
  if (!taskIds.includes(trial.id) || (trial.attempt ?? 1) !== 1 || label.includes("warm") || label.startsWith("smoke")) continue;
  if (trial.harness && trial.harness !== run.harness) continue;
  if (!grouped.has(trial.id)) grouped.set(trial.id, []);
  grouped.get(trial.id).push(trial);
}
const valid = trial => ["success", "failure"].includes(trial.status);
trials = [...grouped.values()].map(rows => {
  rows.sort((a, b) => String(a.started_at ?? "").localeCompare(String(b.started_at ?? "")) || String(a.run_id ?? "").localeCompare(String(b.run_id ?? "")));
  return rows.find(valid) ?? rows.at(-1);
});
const invalid = trials.filter(trial => !valid(trial));
const scored = trials.filter(valid);
const passes = scored.filter(trial => trial.success);
// Baseline effective cost includes known costs in all canonical cells, including invalids.
const costs = numbers(trials.map(trial => trial.cost_first_cold_usd));
const totalCost = costs.reduce((sum, value) => sum + value, 0);
const effectiveCostCoverage = coverage(scored, "cost_first_cold_usd");
const successCosts = numbers(passes.map(trial => trial.cost_first_cold_usd));
const costCoverage = coverage(passes, "cost_first_cold_usd");
const durationCoverage = coverage(passes, "duration_seconds");
const turnsCoverage = passes.length ? passes.filter(t => Number.isInteger(t.turns)).length / passes.length : 0;
const input = t => t.input_tokens ?? t.tokens?.input;
const cached = t => t.cached_input_tokens ?? t.tokens?.cached;
const output = t => t.output_tokens ?? t.tokens?.output;
const cacheRows = passes.filter(t => [input(t), cached(t), t.first_turn_cached_tokens].every(Number.isInteger));
const cacheCoverage = passes.length ? cacheRows.length / passes.length : 0;
const rate = t => input(t) ? Math.max(0, cached(t) - t.first_turn_cached_tokens) / input(t) : null;
const cacheRates = numbers(cacheRows.map(rate));
const inputCoverage = passes.length ? passes.filter(t => Number.isInteger(input(t))).length / passes.length : 0;
const outputCoverage = passes.length ? passes.filter(t => Number.isInteger(output(t))).length / passes.length : 0;
const cacheInput = cacheRows.reduce((sum, t) => sum + input(t), 0);

const candidate = {
  name: args.name ?? run.harness,
  label: args.label ?? run.harness,
  model: run.model,
  provider: run.provider ?? null,
  egress_policy: run.egress_policy ?? null,
  checkpoint: run.checkpoint,
  run_id: run.run_id,
  candidate: true,
  expected,
  full_coverage: scored.length === expected,
  comparable: scored.length === expected && run.methodology_comparable !== false,
  methodology_notes: run.methodology_notes ?? [],
  completed: scored.length,
  valid_coverage: scored.length / expected,
  success_rate_expected: passes.length / expected,
  successful: passes.length,
  infra_invalid: invalid.length,
  pass_rate: scored.length ? passes.length / scored.length : null,

  // Reproducible from raw per-task cost, so directly comparable to the baseline field.
  effective_cost_per_pass: passes.length && costs.length ? totalCost / passes.length : null,
  total_cost_usd: costs.length ? totalCost : null,
  median_cost_per_task: median(costs),
  median_cost_per_success: costCoverage === 1 ? median(successCosts) : null,

  // Success-only metrics require complete success coverage.
  cost_per_success_normalized: costCoverage === 1 ? mean(successCosts) : null,
  median_cost_per_success_normalized: costCoverage === 1 ? median(successCosts) : null,
  cost_per_success_normalized_lower_bound: mean(successCosts),

  median_duration_seconds: durationCoverage === 1 ? median(numbers(passes.map(trial => trial.duration_seconds))) : null,
  cache_hit_rate_typical: cacheCoverage === 1 ? median(cacheRates) : null,
  cache_hit_rate_typical_n: cacheRates.length,
  cache_hit_rate_typical_q1: cacheCoverage === 1 ? quantile(cacheRates, 0.25) : null,
  cache_hit_rate_typical_q3: cacheCoverage === 1 ? quantile(cacheRates, 0.75) : null,
  cache_hit_rate_normalized: cacheCoverage === 1 && cacheInput ? cacheRows.reduce((sum, t) => sum + Math.max(0, cached(t) - t.first_turn_cached_tokens), 0) / cacheInput : null,
  mean_input_tokens: inputCoverage === 1 ? mean(passes.map(input)) : null,
  mean_output_tokens: outputCoverage === 1 ? mean(passes.map(output)) : null,
  input_tokens_coverage: inputCoverage,
  output_tokens_coverage: outputCoverage,
  termination_anomalies: scored.filter(t => t.completed_with_agent_exception).length,
  mean_turns: turnsCoverage === 1 ? mean(passes.map(trial => trial.turns)) : null,

  cost_coverage: costCoverage,
  effective_cost_coverage: expected ? costs.length / expected : 0,
  scored_cost_coverage: effectiveCostCoverage,
  duration_coverage: durationCoverage,
  turns_coverage: turnsCoverage,
  cache_coverage: cacheCoverage,

  task_details: taskIds.map(id => trials.find(t => t.id === id) ?? { id, status: "missing" }).map(trial => ({
    id: trial.id,
    title: trial.title,
    status: trial.status,
    success: Boolean(trial.success),
    cost_first_cold_usd: trial.cost_first_cold_usd ?? null,
    cost_usd: trial.cost_usd ?? null,
    cost_source: trial.cost_source ?? null,
    cost_basis: trial.cost_basis ?? null,
    duration_seconds: trial.duration_seconds ?? null,
    turns: trial.turns ?? null,
    cache_hit_rate_normalized: [input(trial), cached(trial), trial.first_turn_cached_tokens].every(Number.isInteger) ? rate(trial) : null,
    included_in_efficiency: valid(trial) && Boolean(trial.success),
    evidence: trial.evidence,
  })),
};

const out = join(runDir, "candidate.json");
await writeFile(out, `${JSON.stringify(candidate, null, 2)}\n`);

console.log(`${candidate.label}: ${passes.length}/${scored.length} passed (${(candidate.pass_rate * 100).toFixed(1)}%)`);
if (invalid.length) console.log(`${invalid.length} trial(s) marked infra_invalid and excluded from scoring`);
if (scored.length && effectiveCostCoverage < 1) console.log(`cost missing for ${scored.length - numbers(scored.map(t => t.cost_first_cold_usd)).length} task(s); effective_cost_per_pass uses only known costs`);
if (!scored.length) console.log("no scoreable trials: every trial was infra_invalid");
console.log(`wrote ${out}`);

function numbers(values) {
  return values.filter(value => typeof value === "number" && Number.isFinite(value));
}

function coverage(items, field) {
  return items.length ? numbers(items.map(item => item[field])).length / items.length : 0;
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length / 2;
  return sorted.length % 2 ? sorted[Math.floor(mid)] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function quantile(values, q) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * q;
  const low = Math.floor(index);
  return sorted[low] + (sorted[Math.ceil(index)] - sorted[low]) * (index - low);
}

function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
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
