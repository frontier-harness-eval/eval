// Regression test for generate-chart.mjs label placement.
// Reproduces: a candidate at pass_rate >=80% (a *good* third-party result)
// makes the 13th plotted point exhaust the 11-rung dy ladder and the script
// throws "No collision-free label placement", so no chart.svg is written and
// build-report.mjs then dies. This test builds a candidate.json across the
// >=80% band against the real baselines and asserts a chart is produced.
import { mkdtemp, writeFile, mkdir, access, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const here = dirname(fileURLToPath(import.meta.url));
const chart = join(here, "generate-chart.mjs");
const baseline = join(here, "..", "..", "..", "results", "eval-data.json");

const rates = [0.80, 0.8333, 0.8667, 0.90, 0.9333, 0.9667, 1.0];
let pass = 0, fail = 0;
for (const rate of rates) {
  const dir = await mkdtemp(join(tmpdir(), "fh-chart-"));
  const candidate = {
    label: "AiWork.Code 1.0", pass_rate: rate, comparable: false,
    completed: Math.round(rate * 30), expected: 30,
    effective_cost_per_pass: 2.9043, successful: Math.round(rate * 30),
  };
  await writeFile(join(dir, "candidate.json"), JSON.stringify(candidate));
  const res = spawnSync(process.execPath,
    [chart, "--run", dir, "--baseline", baseline, "--display-rank", "true"],
    { encoding: "utf8" });
  let svgOk = false;
  try { await access(join(dir, "report", "chart.svg")); svgOk = true; } catch {}
  const ok = res.status === 0 && svgOk;
  const pct = (rate * 100).toFixed(1).padStart(5);
  if (ok) { pass++; console.log(`  ${pct}%  OK   chart.svg written`); }
  else {
    fail++;
    const why = (res.stderr || res.stdout || "").split("\n").find(l => l.includes("label placement") || l.includes("Error")) || `exit=${res.status}`;
    console.log(`  ${pct}%  FAIL  ${why.trim().slice(0, 90)}`);
  }
  await rm(dir, { recursive: true, force: true });
}
console.log(`\n${pass}/${rates.length} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
