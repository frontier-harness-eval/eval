# GLM-5.3-Flash: four-harness supplementary experiment

This contributor-run experiment evaluates the same 30 tasks with GLM-5.3-Flash
through Zhipu Coding Plan, using four CLI versions from the published Kimi K3
benchmark. The relative ordering differs between these two experiments.
This is an **unranked, non-comparable supplementary result**, not a replacement
for the Kimi leaderboard or a controlled estimate of model quality.

| Harness | Version | Published Kimi K3 | GLM-5.3-Flash | Change in passes |
| --- | --- | ---: | ---: | ---: |
| OpenCode | 1.18.19 | 15/30 (50.0%) | 19/30 (63.3%) | +4 |
| Codex | 0.148.0 | 20/30 (66.7%) | 16/30 (53.3%) | -4 |
| Claude Code | 2.1.237 | 19/30 (63.3%) | 21/30 (70.0%) | +2 |
| Pi (Responses) | 0.84.2 | 18/30 (60.0%) | 19/30 (63.3%) | +1 |

The published counts come from [`results/eval-data.json`](../../eval-data.json)
at benchmark commit `e837a70bd6beb4e72eeeda62dd06e3bd34f6cb63`.
All 120 GLM combinations completed between September 19 and 20, 2026 (UTC).
Each combination uses its first valid executed attempt. Failed executed attempts
were retained; no retries were used to select a higher score.

## Where the differences occur

| Harness | TerminalBench: Kimi / GLM (21 tasks) | DeepSWE: Kimi / GLM (9 tasks) |
| --- | ---: | ---: |
| OpenCode | 15 / 16 | 0 / 3 |
| Codex | 15 / 14 | 5 / 2 |
| Claude Code | 16 / 15 | 3 / 6 |
| Pi (Responses) | 16 / 14 | 2 / 5 |

OpenCode's aggregate increase of four passes comprises six GLM-only passes and
two Kimi-only passes. Codex has three GLM-only passes and seven Kimi-only passes.
The full 120-cell comparison is in [task-comparison.csv](task-comparison.csv).
These observations motivate matched multi-model controls and repeated trials;
they do not establish that GLM is better than Kimi, or identify the cause of the
original OpenCode score. A single pass changes the overall percentage by 3.3 points.

## Method and known differences

- **Runtime:** fresh Docker task containers on one shared Linux host, Harbor
  0.22.0 and datacurve-pier 0.3.1. No Runta golden-checkpoint restore. CLI packages
  were installed inside containers; host CLI installations and login profiles
  were not used. Task resource declarations and timeouts were retained. The
  shared host and caches differ from isolated Runta runtimes.
- **Concurrency:** initially two global trial slots, increased to four at
  2026-09-20 06:35 UTC, one task per harness at a time. Queue pauses and staggered
  completion changed host load during the experiment. Phase durations exclude
  queue idle time; whole-experiment elapsed time is not an efficiency metric.
- **Inputs:** prompts and task TOML files match the frozen benchmark byte for
  byte. [task-manifest.json](task-manifest.json) records their hashes, image tags,
  verifier revisions and verifier-file hashes. The public TerminalBench registry
  source was pinned to `69671fbaac6d67a7ef0dfec016cc38a64ef7a77c`; DeepSWE used the
  revisions recorded per task, including older matching revisions for three tasks.
  Image tags are not a complete digest-pinned runtime snapshot.
- **Network:** Harbor/Pier container egress controls with declared provider and
  dependency hosts, plus the host's sing-box TUN routing. Observed requests to
  `open.bigmodel.cn` were routed direct by sing-box. The original applied Runta
  policy is not available for comparison. [config-profiles.json](config-profiles.json)
  records submitted configuration, not an independently captured complete network
  policy or HTTP request trace.
- **Model serving:** Zhipu Coding Plan `glm-5.3-flash`, not Fireworks Kimi K3.
  OpenCode uses Chat Completions at `/api/coding/paas/v4`; Codex and Pi use
  Responses at `/api/v1`; Claude uses Anthropic Messages at `/api/anthropic`, all
  on `https://open.bigmodel.cn`. Model identity is the requested model ID; no
  server-side model-weight identity was available.
- **Native behavior:** prompts, tools and agent loops remain native to each CLI.
  [Adapters](adapters/) supply model metadata, runner wiring, installation and
  evidence collection. Pi requires a custom Pier adapter. Codex's GLM catalog
  embeds the native fallback prompt from official tag `rust-v0.148.0`, commit
  `3ba0f711642a888aec92a611a3f3b2211157ff89`; it does not replace that prompt with
  empty instructions. Pi's earlier Chat Completions diagnostic is excluded.
- **Budgets:** max reasoning was requested (Pi's xhigh maps to max). Output caps,
  context handling and compaction are not identical across CLIs. OpenCode's
  observed main-loop output cap was 32,000; Pi and Claude were configured for
  32,000. Codex lacks the same native output-cap override in this version.
  Declared context metadata does not prove equal effective context windows.
- **Repairs:** three pre-agent setup attempts are excluded: OpenCode regex
  (Node download host missing from egress policy), Claude regex (bootstrap TLS),
  and OpenCode DB WAL recovery (NVM Git clone TLS). Each repair used a new attempt
  ID and retained the original evidence. Claude switched to npm installation of
  the same 2.1.237 package; the remaining OpenCode tasks used NVM's script install
  method with the same Node major and OpenCode version. Installation changes
  occurred during the sweep and are represented by separate config profiles.
- **Verifier inputs:** Cython used a read-only public upstream source bundle at
  `/app/pyknotid.bundle`, matching the task-supplied source, to avoid a network
  fetch. This provision was applied to all four harnesses. It is disclosed as
  an environment change, not a reason to infer baseline comparability.
- **Failures:** post-execution timeouts and errors remain end-to-end failures.
  In particular, Claude's `gcode-to-text` attempt ended with API HTTP 400,
  provider code 1210 (image format/parsing error); this is not a pure coding
  failure. Exception types and raw verifier rewards are retained per trial.
  CTRF summaries are emitted by each verifier and can group parameterized tests;
  scores use the binary verifier reward, not CTRF test counts.
- **Cost:** per-task subscription billing is unknown, so costs are null. Native
  zero costs or estimates are not treated as paid amounts. No cost frontier or
  cost-efficiency comparison is claimed.

## Public artifacts and reproducibility

- [results.json](results.json): all 120 selected outcomes, timings, verifier
  rewards, exception types, aggregate counts and hashes of locally retained
  evidence. These are contributor-reported results, not independently validated
  by maintainers. Hashes identify retained files; they do not substitute for
  public raw evidence.
- [config-profiles.json](config-profiles.json): deduplicated submitted runner
  settings referenced by each trial. `${EVAL_ROOT}` is a portable placeholder;
  credential fields contain environment references only.
- [task-manifest.json](task-manifest.json): task input and verifier provenance.
- [adapters/](adapters/) and [python-requirements.lock](python-requirements.lock):
  the adapter code, Codex metadata and captured Python dependency versions.
  Native Codex content attribution is recorded in [adapters/NOTICE.md](adapters/NOTICE.md).
- [validate.py](validate.py): recomputes counts and paired outcomes, checks task
  hashes and validates the published CSV against the JSON and baseline.

Run the read-only consistency check from any working directory:

```sh
python3 results/supplementary/2026-09-glm-5.3-flash/validate.py
```

For a new paid evaluation, reconstruct task directories from the pinned public
sources in the manifest, place the adapters on `PYTHONPATH`, expand
`${EVAL_ROOT}`, and supply provider credentials through environment variables.
Combine each trial's config profile (remove its descriptive `runner` field) with
its task directory and a fresh job name; use the matching Harbor or Pier runner.
The source bundle, container dependencies, public verifiers and native CLI
packages must also be provisioned. These artifacts are a reproduction reference,
not a turnkey replay script or a byte-identical golden runtime.

Credentials, host paths, container identifiers, raw model conversations, solution
patches and private verifier artifacts are not included in this contribution.
The existing Kimi dataset and leaderboard remain unchanged.
