# Running Raven-Code on FrontierHarness

A step-by-step recipe for reproducing this submission. It mirrors what `raven-code-dsv41-20261112` actually ran: Harbor 0.22.0, local Docker, the `raven_code_harbor` adapter, and Raven-Code at the pinned commit.

**Scope.** This evaluates **Raven-Code**, the coding harness - its entry point is `agents/raven-code/run.py`, which the adapter runs once per attempt:

```bash
python agents/raven-code/run.py --task "<instruction>" --workspace "$PWD" \
  --config <rendered.json> --job harbor-trial --timeout 0 --verbose
```

It does **not** use `raven host`, the multi-tenant host process that serves EverMe deployments; nothing in this submission starts it. The harness runs with `--timeout 0`, so the task budget comes from `task.toml` through Harbor, not from the harness.

## 1. What you need

| Requirement | Notes |
|---|---|
| Linux host with Docker | This run used one 4 vCPU / 14 GiB host at concurrency 2. Each trial builds its own task container; size the host for `concurrency x task vCPU`, and budget ~40 GB for images plus ~150 MB of job artifacts per 248 attempts. |
| Python 3.12 | Harbor 0.22.0 and the adapter both run on it. |
| Harbor 0.22.0 | `harbor` CLI plus the task packages it downloads on first use. |
| An OpenAI-compatible provider key | DeepSeek official API here (its model id `deepseek-flash` serves DeepSeek-V4.1-1017); Baseten, OpenRouter and others work with the right base URL. |
| Network to the task images and to PyPI/GitHub | Many `test.sh` scripts download their own tooling at scoring time; see section 8. |

## 2. Install the adapter

```bash
git clone https://github.com/EverMind-AI/Raven
uv pip install -e /path/to/harbor-adapter      # depends on harbor==0.22.0
```

The adapter exposes one class, `raven_code_harbor:RavenCodeAgent`. It implements Harbor 0.22's `BaseInstalledAgent` lifecycle:

1. **install**: clone Raven at `RAVEN_COMMIT`, `uv sync --frozen --no-dev`, write a memory-off `RAVEN_HOME`.
2. **run**: render a benchmark config (provider, model, effort, memory off), run one `run.py --task ... --workspace ...` turn, copy the session and usage evidence into `/logs/agent/`.
3. **AgentContext**: filled from the telemetry (input, output and cached tokens, cost when the provider reports it).

## 3. Provider and harness settings

| Variable | Default | Meaning |
|---|---|---|
| `RAVEN_API_KEY` | - | Preferred key; otherwise `DEEPSEEK_API_KEY`, `BASETEN_API_KEY`, `OPENROUTER_API_KEY` |
| `RAVEN_API_BASE` | `https://api.deepseek.com` | OpenAI-compatible base URL |
| `RAVEN_MODEL` | Harbor `-m` | Overrides the model id |
| `RAVEN_EFFORT` | `max` | `reasoningEffort` |
| `RAVEN_COMMIT` | `147297b6e6501de0f279a4aadc687ee9f701260e` | Raven commit to install |
| `RAVEN_MAX_TOKENS` | `65536` | Max output tokens per model call |
| `RAVEN_CONTEXT_WINDOW` | `1048576` | Context window advertised to the harness |

The rendered config also fixes `maxToolIterations: 150`, `llmCallTimeout: 1800` and compaction on. Those are the settings this submission used.

## 4. Smoke test with one task

```bash
export RAVEN_API_BASE=https://api.deepseek.com
export DEEPSEEK_API_KEY=...
harbor run -d terminal-bench@2.0 -i openssl-selfsigned-cert \
  --agent-import-path raven_code_harbor:RavenCodeAgent \
  -m deepseek-flash -k 1 -n 1 \
  --jobs-dir ./jobs/raven-smoke
```

Use one short task and one attempt to prove the plumbing before spending a full budget. Watch `jobs/raven-smoke/<job>/<trial>/verifier/test-stdout.txt` for the verifier and `agent/raven-code.log` for the harness.

## 5. The full job

Write a job config (the file this run used, minus machine paths):

```json
{
  "job_name": "2026-11-12__14-38-07",
  "jobs_dir": "jobs/raven-62x4",
  "n_attempts": 4,
  "n_concurrent_trials": 2,
  "agent_setup_timeout_multiplier": 10.0,
  "debug": true,
  "environment": {
    "type": "docker",
    "extra_docker_compose": ["golden/raven-local-overlay.yaml"]
  },
  "agents": [{"name": "raven_code_harbor:RavenCodeAgent", "model_name": "deepseek-flash"}],
  "datasets": [{
    "name": "frontier-harness-eval/frontier-harness-eval",
    "ref": "sha256:9236400fc1a6619eb72a663445c580417be9bbbab32f816c7dff76d0a96ab24a"
  }]
}
```

```bash
harbor job start -c job.json
# equivalent shorthand:
harbor run -c job.json
```

`--print-config` resolves the config without starting anything, which is the quickest way to catch a bad path or dataset ref.

### The prebuilt overlay

`golden/raven-local-overlay.yaml` mounts a prebuilt Raven tree into every task container:

```yaml
services:
  main:
    volumes:
      - /path/to/prebuilt-src/Raven:/opt/raven:ro
      - /path/to/prebuilt-src/uv-python:/opt/uv-python:ro
```

Two rules:

- The file is pinned by digest in the job lock. **Do not edit it for a running job**; a changed digest can make `harbor job resume` refuse the lock. To relocate the prebuilt, keep the file content identical and create the same absolute paths, or start a new job.
- `/opt/raven/.raven-prebuilt-commit` must hold the commit you intend to test. When it matches `RAVEN_COMMIT`, the per-trial clone and `uv sync` are skipped and the attempt starts in seconds; when it does not, every attempt pays the clone and sync cost and many budgets will not survive it.

Build the prebuilt on the same architecture as the host, and keep the Python in `/opt/uv-python` reachable: a prebuilt venv built for arm64 does not run in an amd64 container.

## 6. Monitor and resume

Run the controller inside tmux, because `harbor job resume` restarts in-flight trials rather than reattaching to their containers:

```bash
tmux new-session -d -s raven 'harbor job resume -p ./jobs/raven-62x4/2026-11-12__14-38-07 2>&1 | tee -a logs/resume.log'
```

Progress lives in the job's `result.json` (`stats`, `finished_at`); one directory per attempt under the job dir. A summary script:

```python
import json, glob, collections
job = "jobs/raven-62x4/2026-11-12__14-38-07"
c = collections.Counter()
for p in glob.glob(job + "/*/result.json"):
    r = json.load(open(p))
    c[(r.get("exception_info") or {}).get("exception_type")] += 1
print(c)
```

### Recovering from failures

| Situation | Command | Effect |
|---|---|---|
| Infrastructure error (network, image, registry) | `harbor job resume -p <job>` | Retries only trials that have no result yet. Trials that ended with an exception keep their result, so they are **not** retried. |
| Retry a class of errors | `harbor job resume -p <job> -f VerifierTimeoutError -f RuntimeError` | Deletes the matching trial directories and refills them. Back up the job dir first: this is `shutil.rmtree` on matched trials. |
| The agent finished but the verifier failed on its own downloads | `harbor job regrade` | Re-runs verification from the recorded trials without another agent run. It acts on the job as a whole, so back up the job dir first. |
| Cancel a trial that a crash left half-written | move its directory out of the job dir, then resume | A `CancelledError` or partial `result.json` counts as done; moving the directory makes Harbor refill the attempt. |

Two operational notes:

- **Harbor resolves each task's package version on its registry before a trial**, even when every image is cached. A registry outage (one HTTP 520 here) retries until it gives up and takes the whole controller down. Recovery is: wait for the registry to answer, move any `CancelledError` trial aside, resume. Run the controller under a small watchdog if the run is unattended.
- **`harbor job resume` does not reset the balance**, so check that the provider key has quota before starting a long unattended job.

## 7. Read the results

Per attempt, under `<job dir>/<task>/<attempt name>/`:

| Path | Content |
|---|---|
| `result.json` | Outcome: `verifier_result.rewards.reward`, `exception_info`, start and finish times |
| `verifier/test-stdout.txt` | Verifier output, including the task's own failed assertions |
| `verifier/ctrf.json` | Per-test status and traces |
| `agent/raven-code.log` | Launcher log: model, workspace, exit code, elapsed seconds |
| `agent/raven-usage.jsonl` | One record per model call (tokens, finish reason) and per tool call (name, timestamp) |
| `agent/raven-state/` | Rendered config, tool documentation, session transcript for attempts that ended normally |

Scoring rules used here:

- **Score per attempt**, not per task: `passed / attempts`. Reporting "tasks that passed at least once" separately avoids turning a 4-attempt job into a best-of-four headline.
- **Never rerun a passing attempt.** Resuming with `-f` on a trial that already scored 1.0 throws that pass away.
- **Keep the denominator honest.** An attempt that scored 0 because the verifier could not install its own tooling is marked `verifier_infra` and reported separately; it is not a wrong answer. Detect it by a reward of 0 with no `ctrf.json` and `uvx: command not found` in `test-stdout.txt`.

## 8. Things that will bite

- **Task containers build per trial.** Pre-pull the environment images if the registry is slow; `EnvironmentStartTimeoutError` is usually an image pull, and it can leave an orphan container behind.
- **Multi-arch images.** If only the platform you did not intend is in the local store, Docker runs the other architecture under emulation and the agent's prebuilt Python fails with `Could not open '/lib64/ld-linux-x86-64.so.2'`. Pull the intended platform and pin it.
- **Scoring-time downloads.** `test.sh` installs pytest (often through uv) at scoring time. On a slow or filtered network this fails silently as a score of 0; consider a transparent egress proxy for containers, with the provider and the package mirrors excluded so keys and prompts never traverse a third party.
- **Command ceiling vs task budget.** Raven's `exec` allows one command to run 600 s; many task budgets are 900-1800 s and the harness is not told how much budget remains. A single blocking command can consume the whole budget.
- **Reasoning effort `max` can run away.** A model call that spends the entire `maxTokens` budget on reasoning returns nothing (`finish_reason: length`). It is visible in `raven-usage.jsonl`, and it costs both time and money.
- **Killed attempts keep no session transcript.** The transcript is written at the end of a turn, so attempts killed at the budget keep only the usage ledger.
- **The rendered config contains the provider key in plaintext.** The adapter keeps the key off the command line on purpose (it passes it through the exec environment), but `run.py` renders the provider block - including `providers.<name>.apiKey` - into `.config.rendered.*.json` under the agent state dir, and the adapter copies that whole directory into `/logs/agent/raven-state/`. Treat it as secret: scrub it before sharing evidence, and rotate the key if one was published. Fixing this at the adapter means redacting the key from the rendered config before the copy.

## 9. Cost and time

This run: 248 attempts, 60.5 agent-hours of execution spread over six days of wall time, 11.5M prompt tokens + 1.08B cached-prompt tokens + 17.5M completion tokens, about CNY 121 at DeepSeek's list prices. The v1.1 tasks dominate: 68 attempts used 63 CNY and 23 agent-hours because most of them run for their full budget.
