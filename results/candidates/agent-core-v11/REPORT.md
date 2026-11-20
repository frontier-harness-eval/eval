# Agent Core on FrontierHarness v1.1

## Summary

**Agent Core**, the proprietary Go-based harness behind Alibaba’s AI product for Taobao merchants, completed one scored sweep of all 62 pinned FrontierHarness v1.1 tasks across five models on Runta. With Fireworks at max reasoning effort, the run recorded **191/310 passes (61.6%) after lookup review**, with an estimated **$1.057 in model cost per pass** and **27.9 minutes of agent-plus-verifier time per pass**. We’re submitting these candidate results for maintainer reproduction and consideration in the next FrontierHarness run.

| Metric | Agent Core |
| --- | ---: |
| Raw verifier | 195/310 (62.9%) |
| After lookup review | 191/310 (61.6%) |
| After lookup review and strict timeout scoring | 180/310 (58.1%) |
| Reviewed by task suite | Terminal-Bench 2.1 180/225 · Terminal Bench 4 11/85 |
| Observed model spend across scored trials | $224.27 |
| Trials with complete model cost | 272/310 |
| Observed input-token cache rate | 95.3% |

| Model | Raw verifier | After lookup review | Strict timeout after lookup review |
| --- | ---: | ---: | ---: |
| GLM-5.3 | 36/62 | 35/62 | 34/62 |
| GLM-5.3-Flash | 41/62 | 41/62 | 37/62 |
| DeepSeek-V4.1-Flash-1017 | 42/62 | 40/62 | 38/62 |
| Muse Spark Open | 36/62 | 35/62 | 33/62 |
| Kimi-K3 | 40/62 | 40/62 | 38/62 |

## Setup

- **Harness.** Agent Core at `897e95d5c8bf30ede82e7dc7ef7d31a03faef819`, built for Linux amd64 with Go 1.25.9.
- **Runner.** Harbor 0.25.0 with native Runta. Each attempt used a fresh VM and task container with the pinned `frontier-harness-eval@v1.1.0` task, its verifier, and its time limit. The run used up to eight concurrent trials after resumption.
- **Models.** All five models served by Fireworks with `reasoning_effort=max`, a 500,000-token harness context window, and a 64,000-token main-loop output budget. GLM-5.3 ran in text-only mode.
- **Search.** Tavily was enabled. Runta supplied the Fireworks and Tavily credentials through separate egress rules.

## How Agent Core was run

In the merchant product, the desktop client hosts Agent Core. For the benchmark, a Python adapter launched the same engine headlessly inside each task container and drove it through stdio JSON-RPC. The adapter initialized the engine, applied the run configuration, opened a fresh session, and passed the task instruction as the user prompt. Harbor ran the task verifier and recorded the reward.

The evaluated configuration used the Core model and tool loop, six-zone context compaction, progressive tool disclosure, shell and file tools, image input where configured, local subagents, and Tavily search. The standalone profile omits the merchant desktop UI and account services.

## Candidate materials

- [trial-results.csv](trial-results.csv) contains one row per scored task/model pair, with task digests, verifier and reviewed scores, timeout flags, timing, usage, and pricing coverage.
- [REPRODUCTION.md](REPRODUCTION.md) records the source and dataset revisions, binary checksums, runner configuration, launch commands, and scoring formulas.
- The pinned Linux binary, Harbor adapter, and original Harbor jobs are retained for maintainer verification. The jobs include the 310 scored trajectories, verifier output, error logs, and available provider usage receipts.

## Disclosed deviations

1. **Provider and repetitions.** The published v1.1 Live run used Baseten and four scored attempts per task and model. This candidate used Fireworks and one scored attempt per pair. No matched-provider control was run.
2. **Scoring.** Four verifier passes were scored as failures after a trajectory review found direct access to task-specific reference material. The 191-pass result retains 11 verifier passes with an agent timeout marker, consistent with how the published Live feed counts a passing outcome with that marker. The 180-pass result applies strict timeout scoring to the same reviewed trials. All 310 remain in the denominator.
3. **Recovery.** We resumed the sweep after infrastructure interruptions and tracked 87 canceled or infrastructure/execution-error records outside the scored set. The result table has one scored record for each task/model pair. One reward was recovered from a verifier that completed before the trial cancellation was recorded.
4. **Cost coverage.** Fireworks list prices were applied to observed usage. There are 44 missing usage receipts across 38 scored trials. The Live-style cost-per-pass estimate uses the mean of available complete costs per task, averaged across covered tasks and divided by the reviewed pass rate.
5. **Source access.** Agent Core is closed source. The evaluated Linux binary is pinned by SHA-256, and the adapter and original jobs can be provided through a private channel agreed with the maintainers.

## Verification

From the directory containing `trial-results.csv`, this command checks the three reported totals:

```sh
awk -F, 'NR > 1 {
  n++; raw += $6; reviewed += $7
  if ($9 == "false") strict += $7
} END { print n, raw, reviewed, strict }' trial-results.csv
# 310 195 191 180
```

Harbor’s dry run resolved 62 trials for each of the five model configurations. The pinned binary, adapter, and original job archives are available for maintainer reproduction through an agreed private channel.
