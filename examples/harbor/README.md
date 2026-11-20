# Harbor evaluation examples

Minimal, runnable examples of evaluating a coding agent with
[Harbor](https://pypi.org/project/harbor/) `0.22.0`, the version this repository pins.
They run on local Docker and are independent of the FrontierHarness scripts.

| File | What it shows |
| --- | --- |
| `tasks/hello-sum/` | A complete task: `instruction.md`, `environment/Dockerfile`, reference `solution/solve.sh`, and `tests/test.sh`, which writes the reward to `/logs/verifier/reward.txt` |
| `my_agents/my_harness.py` | A custom agent adapter (`BaseInstalledAgent`) that installs a CLI harness at a pinned commit, runs it, and reports token usage |
| `job.yaml` | A job config comparing the oracle with the custom agent on a local task and one Terminal-Bench task |
| `run_eval.py` | The same job built and run from Python, printing per-trial reward and tokens |
| `summarize.py` | Pass rate, errors and cost per agent from an existing jobs directory |

`my_harness.py` is a template: `acme/my-harness` and its CLI flags are placeholders
for your harness's real install and run commands.

## Prerequisites

Docker with Compose v2, and:

```bash
uv tool install 'harbor==0.22.0'
```

Run every command below from this directory.

## Check the task with the oracle (no model calls)

The oracle applies `solution/solve.sh`. It must score 1 before an agent's score means anything.

```bash
harbor run -p tasks/hello-sum -a oracle -y
```

## Run the custom agent

```bash
export FIREWORKS_API_KEY=...
PYTHONPATH=. harbor run -p tasks/hello-sum -a my_agents.my_harness:MyHarness \
  -m fireworks_ai/accounts/fireworks/models/kimi-k3 \
  --ae 'FIREWORKS_API_KEY=${FIREWORKS_API_KEY}' -y
```

Harbor resolves the quoted `${FIREWORKS_API_KEY}` reference at agent setup.
The job configuration stores the variable reference.

## Run the job config, or the same job from Python

```bash
harbor run -c job.yaml --print-config   # resolve without running
PYTHONPATH=. harbor run -c job.yaml
PYTHONPATH=. uv run --with harbor==0.22.0 python run_eval.py
```

## Inspect results

Each trial writes `jobs/<job>/<trial>/result.json` with `verifier_result.rewards.reward`,
`agent_result` (tokens and cost), `exception_info` and timing.

```bash
python3 summarize.py jobs/hello-sum-oracle-vs-harness
harbor view jobs
```

## Notes

- Terminal-Bench images are `linux/amd64`; on Apple Silicon they run under emulation.
- Pier (used for DeepSWE) follows the same adapter pattern with its own base class,
  loaded with `pier run --agent-import-path`. A Harbor adapter does not load in Pier.
- To plug an adapter into this repository's local runner, pass it with
  `--harbor-agent-import-path my_agents.my_harness:MyHarness`.
