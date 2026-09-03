# MiniMax Code through Harbor

Use this profile when the harness under evaluation is
[MiniMax Code](https://github.com/MiniMax-AI/minimax-code). It reuses Harbor's MCode
adapter and replaces only its networked install step with a checkpointed bundle. This
keeps setup functional for no-network tasks without opening npm or Node download hosts
to the agent or verifier phases.

| Component | Pinned version |
| --- | --- |
| Harbor | `0.22.0` |
| Node.js | `22.23.2` |
| `@minimax-ai/code` | `0.2.7` |
| Harbor adapter | `mcode` via `OfflineMCode` |
| Terminal-Bench 2.1 | `sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a` |

Run these commands from the repository root:

```bash
FH=skills/frontierharness-eval/scripts
export RUNTA_TOKEN=rt_...
export FIREWORKS_API_KEY=...  # or the key selected with --provider
```

## Provision the golden checkpoint

The public `tasks/` directory identifies the 21 Terminal-Bench tasks and the nine
DeepSWE-derived tasks. Copy it into the checkpoint to preserve a digest of the
published definitions. The provisioner downloads Terminal-Bench from the content
digest above and clones DeepSWE at the commit below, retains the complete environment
and verifier assets, then overlays all 30 matching `task.toml` and `instruction.md`
files from this repository:

```bash
$FH/provision-golden-checkpoint.sh \
  --runtime fh-build-mcode \
  --checkpoint fh-golden-mcode-0.2.7 \
  --harness mcode \
  --harness-version 0.2.7 \
  --harbor-version 0.22.0 \
  --harbor-only \
  --provider fireworks \
  --copy-tasks tasks \
  --prepull-tasks tasks \
  --deep-swe-ref 435ee89ec2f2e2289f33b0da4f992f0b7b7266b9 \
  --cpus 4 --memory 8192
```

The manifest records the versions, source refs, overlay counts, copied-definition
digest, and the generated MCode bundle digest. During provisioning, Node and the pinned
npm package are downloaded once into an x86_64 Linux bundle. Each task setup then
uploads that bundle and verifies its checkpointed SHA-256 before using Harbor's normal
MCode configuration and execution paths. `--repo` and `--commit` are intentionally
omitted because the evaluated adapter is part of the pinned Harbor release.

Before running trials, verify that the manifest has `task_count: 30`,
`terminal_bench_overlay_count: 21`, and `deep_swe_overlay_count: 9`, plus non-empty
`tasks_sha256` and `mcode_bundle_sha256` values. Any other value means provisioning did
not reproduce the published task set.

## Smoke-test the integration

Render the command first. This does not need credentials or a runtime:

```bash
$FH/run-minimax-code.sh --provider fireworks --print-command
```

Then run one task from a fresh restore before spending a full sweep:

```bash
printf '%s\n' terminal-bench/regex-log > tasks-mcode-smoke.txt

$FH/run-minimax-code.sh \
  --checkpoint fh-golden-mcode-0.2.7 \
  --provider fireworks \
  --run-id mcode-0.2.7-smoke \
  --tasks tasks-mcode-smoke.txt
```

Confirm that the collected Harbor job reports `agent_info.name` as `mcode`,
`agent_info.version` as `0.2.7`, and contains `mcode.jsonl` before starting the full
run. A model response without a verifier result is not a successful smoke test.

## Run the published task set

```bash
jq -r '.harnesses[0].task_details[].id' results/eval-data.json > tasks-mcode.txt

$FH/run-minimax-code.sh \
  --checkpoint fh-golden-mcode-0.2.7 \
  --provider fireworks \
  --run-id "$(date +%Y-%m-%d)-mcode-0.2.7" \
  --tasks tasks-mcode.txt
```

`run-minimax-code.sh` delegates restore, evidence collection, and retry semantics to
`run-trials.sh`, but replaces both suite defaults with Harbor commands over the two
checkpointed local task directories. It uses `OfflineMCode`, a thin subclass of
Harbor's adapter that changes only installation. The provider hostname passed with
`--allow-agent-host` opens egress during `agent.run()` while setup and verification
retain the task's baseline network policy.

## Provider mapping

MiniMax Code registers a custom BYOK provider from Harbor's model connection. The
profile supplies `api_format=openai-completions` and translates provider routes where
the endpoint is otherwise unavailable to the adapter:

| `--provider` | MCode model | Connection behavior |
| --- | --- | --- |
| `fireworks` | `openai/accounts/fireworks/models/kimi-k3` | Maps `FIREWORKS_API_KEY` to the OpenAI-compatible Fireworks endpoint |
| `moonshot` | `openai/kimi-k3` | Maps `MOONSHOT_API_KEY` to Moonshot's global endpoint |
| `openrouter` | `openrouter/moonshotai/kimi-k3` | Uses Harbor's native OpenRouter connection |
| `together` | `together/moonshotai/Kimi-K3` | Uses Harbor's native Together connection |

The route translation changes only the client protocol. The evaluated model remains
Kimi K3. `custom` is not accepted by this profile because it cannot safely infer a base
URL, secret alias, API format, and egress host; use `run-trials.sh --cmd` explicitly for
a private gateway.

Harbor disables MCode's login-backed native `web_search` for BYOK runs, retains local
`web_fetch`, and forwards task MCP servers. This prevents benchmark behavior from
depending on accidental MiniMax account login state.

## Result caveat

MCode's JSONL stream exposes input, cache-read, and output token counts, which Harbor
collects into the agent context. It does not expose provider cost, so cost fields remain
empty unless they are joined from provider billing data. Do not substitute an estimate
silently; state the source and method if cost is added before normalization.
