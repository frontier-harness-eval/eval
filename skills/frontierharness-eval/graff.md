# graff through Harbor and Pier

Use this profile when the harness under evaluation is
[graff](https://github.com/justrach/codegraff) (`justrach/codegraff`). Harbor and Pier
do not ship a built-in graff adapter, so this profile registers a thin custom agent
that uploads a **checkpointed** Linux binary into each task container and runs
`graff --json --yolo -p`. That keeps setup off GitHub during trials (the skill's
egress allowlist does not include `github.com`) without changing Harbor or Pier's
normal configuration, execution, or scoring paths.

| Component | Pin |
| --- | --- |
| graff | `v0.0.286` (`68540a541e13dac127c7bb4523f77f736601b186`) |
| Linux x86_64 tarball SHA-256 | `2098a13099ee9a645a5a535d04fe5fd8f2602181a93542a3e4b1498ba28474d8` |
| Linux aarch64 tarball SHA-256 | `bdfd1c1cbb365b729c6e2b1d6c6020085c6344f70fb9e1651bb3a84d1f1df4c0` |
| Harbor | `0.22.0` (skill default) |
| Pier | `datacurve-pier==0.3.1` (skill default) |
| Adapters | `frontierharness_graff:Graff` (Harbor), `frontierharness_graff_pier:Graff` (Pier) |

Run these commands from the repository root:

```bash
FH=skills/frontierharness-eval/scripts
export RUNTA_TOKEN=rt_...
export FIREWORKS_API_KEY=...  # or the key selected with --provider
```

## Provider mapping

graff speaks Fireworks, Moonshot, and OpenRouter natively. The adapter strips Harbor's
LiteLLM prefix and leaves graff's own model id. Together is not a first-class graff
provider, so this profile refuses it rather than silently routing through another host.

| `--provider` | LiteLLM route (Harbor/Pier `-m`) | graff `--model` | Key |
| --- | --- | --- | --- |
| `fireworks` (default) | `fireworks_ai/accounts/fireworks/models/kimi-k3` | `accounts/fireworks/models/kimi-k3` | `FIREWORKS_API_KEY` |
| `moonshot` | `moonshot/kimi-k3` | `kimi-k3` | `MOONSHOT_API_KEY` |
| `openrouter` | `openrouter/moonshotai/kimi-k3` | `moonshotai/kimi-k3` | `OPENROUTER_API_KEY` |

The evaluated model remains Kimi K3. `custom` is not accepted here because a private
gateway needs a base URL graff does not infer; use `run-trials.sh --cmd` for that.

graff reads the provider key from the environment. Runta injects a stub that the
egress proxy swaps on the provider host, so the real key never lands in the
checkpoint or the task container.

## Provision the golden checkpoint

```bash
$FH/provision-golden-checkpoint.sh \
  --runtime fh-build-graff \
  --checkpoint fh-golden-graff-0.0.286 \
  --harness graff \
  --provider fireworks \
  --repo https://github.com/justrach/codegraff \
  --commit 68540a541e13dac127c7bb4523f77f736601b186 \
  --cpus 4 --memory 8192 --disk-size-gib 100 \
  --prepull-tasks tasks \
  --install-script "$FH/install-graff.sh"
```

`install-graff.sh` downloads the pinned GitHub-release tarball for the runtime's
architecture, checks the SHA-256 above, and installs the binary at `/work/graff/graff`.
The provisioner also copies `skills/frontierharness-eval/agents/*.py` to `/work/` so
Harbor and Pier can import them with `PYTHONPATH=/work`. Confirm the checkpoint
manifest records `graff_version` `0.0.286` and a matching `graff_sha256` before
running trials.

## Smoke-test the integration

Render the commands first. This does not need credentials or a runtime:

```bash
$FH/run-graff.sh --provider fireworks --print-command
```

Then run one Terminal-Bench task and one DeepSWE task from a fresh restore before
spending a full sweep:

```bash
printf '%s\n' terminal-bench/regex-log datacurve/anko-typed-variable-bindings > tasks-graff-smoke.txt

$FH/run-graff.sh \
  --checkpoint fh-golden-graff-0.0.286 \
  --provider fireworks \
  --run-id graff-0.0.286-smoke \
  --tasks tasks-graff-smoke.txt
```

A successful smoke test has `agent_info.name` `graff`, `agent_info.version` containing
`0.0.286`, a `graff.jsonl` transcript, and a verifier result. A model response without
a verifier result is not a successful smoke test.

## Run the published task set

```bash
$FH/run-graff.sh \
  --checkpoint fh-golden-graff-0.0.286 \
  --provider fireworks \
  --run-id "$(date +%Y-%m-%d)-graff-0.0.286"
```

With no `--tasks`, this is the published 30-task set. `run-graff.sh` delegates restore,
evidence collection, and retry semantics to `run-trials.sh`, and overrides the two
suite templates so Harbor and Pier load the custom adapters.

## Result caveat

graff's `--json` `turn` events expose `cost_usd`, `input_tokens`, and
`cache_read_tokens`. The adapters copy those into Harbor/Pier's agent context when
present. If a trial's JSONL has no `turn` event, cost fields stay empty — do not
substitute an estimate. This PR adds the workflow, not a leaderboard row: a comparable
score still needs a full 30-task sweep on Kimi K3 from a golden checkpoint.

## What this profile deliberately does not do

- It does not install graff from `latest` or build Zig inside the task container.
- It does not enable `graff login` / subscription OAuth. BYOK only, matching the
  published Fireworks baselines.
- It does not run DeepSWE through Harbor. Pier's per-agent allowlist is what lets the
  harness reach the provider on `allow_internet = false` tasks.
