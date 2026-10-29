# AiWork.Code (agentix / dtcoder) — FrontierHarness Eval profile

**Organization:** Ant Digital Technologies

FrontierHarness Eval v1 holds the model constant at **Kimi K3** and compares
*harnesses*. This profile evaluates the **AiWork.Code** harness — agentix and its
`dtcoder` CLI — reusing **Harbor 0.22.0** for the 21 Terminal-Bench tasks and
**Pier 0.3.1** for the 9 DeepSWE tasks, with Kimi K3 served over Moonshot's
OpenAI-compatible wire (`https://api.moonshot.cn/v1`).

No official script or task is modified by this profile. The two upstream changes
that ship alongside it are unrelated repairs to the candidate rendering path
(see *Upstream fixes* below).

## Files

| file | role |
|---|---|
| `frontierharness_aiwork.py` | Harbor agent `AiworkAgent(BaseInstalledAgent)`: offline install of the `dtcoder` binary, Kimi K3 / Moonshot config, daemon start, one `dtcoder chat --json` turn tee'd to `/logs/agent/dtcoder.txt`, and usage recovered into `AgentContext` |
| `pier_aiwork.py` | Pier agent `Aiwork(BaseAgent)` wrapping the same dtcoder agent; routes its exec through Pier's plumbing and pins the network allowlist to `api.moonshot.cn` |
| `pier_environment.py` | Preserves Pier's native verifier-evidence mounts when the Runta CA bind mount is added |
| `run_task.py` | `--cmd` target for `scripts/run-trials.sh`: dispatches `{suite}` → Harbor / Pier in Python (never a shell string compare), emits the runner config, translates one native `result.json` into the top-level `{reward, native_result, exception_info}` |
| `aiwork-model-settings.json` | Kimi K3 metadata; single source of truth for the context/output limits |
| `test_profile.py` | Offline test suite (see below) |
| `requirements.txt` | `harbor[modal]==0.22.0`, `datacurve-pier==0.3.1`, `runta-sdk[harbor]==0.2.0` |

## Prerequisites

1. A prebuilt **`dtcoder` binary** at `/work/frontierharness/dtcoder` (and,
   optionally, `libagentix_ce_dtdag.so` alongside it). Build it so it embeds no
   private or first-party endpoints — verify with `strings` that only the public
   provider endpoint is present, since a public submission must not leak internal
   hosts. If per-call token profiling is disabled by default in that build,
   re-enable it to keep per-call token data.
2. A Moonshot CN key exported as `MOONSHOT_API_KEY` on the eval host. It is
   injected on egress by Runta's secret rule, never baked into the image.

## Running

```sh
scripts/run-trials.sh \
  --checkpoint <golden> --harness aiwork-code --provider custom \
  --model openai/kimi-k3 --run-id <run> --out runs/<run> \
  --secret-name MOONSHOT_API_KEY --secret-host api.moonshot.cn \
  --cmd 'python3 /work/frontierharness/run_task.py --root /work/frontierharness --suite {suite} --task {task} --model {model} --jobs {jobs}'
```

- `--provider custom` **requires `--secret-host api.moonshot.cn`** (the `moonshot`
  preset points at `api.moonshot.ai`, the wrong endpoint for K3) and
  `--secret-name MOONSHOT_API_KEY`; omit the latter and every trial 401s with no
  diagnostic.
- The `--cmd` is passed **without quotes around `{suite}`**: `run-trials.sh`
  shell-quotes each placeholder, so `[ "{suite}" = ... ]` would never match.
  `run_task.py` dispatches in Python, avoiding the trap entirely.

Reporting (so the candidate appears on the scatter plot):

```sh
node scripts/normalize-results.mjs --run runs/<run> --name aiwork-code --label "AiWork.Code"
node scripts/generate-chart.mjs   --run runs/<run> --display-rank true   # <- required
node scripts/build-report.mjs     --run runs/<run>
```

`--display-rank true` is mandatory: `run-trials.sh` hard-codes
`methodology_comparable:false`, which otherwise filters the candidate off the plot.

## Offline tests

`python test_profile.py` (with the pinned Harbor/Pier installed) — no model call,
no container, no Runta. Nine cases pass:

1. Every `tasks/*/task.toml` round-trips through `configuration()` and validates
   against the real Harbor/Pier `JobConfig`, with no timeout/resource overrides —
   counts asserted `{harbor: 21, pier: 9}`.
2. Context/output limits come from `aiwork-model-settings.json`.
3. `name()` == `"aiwork-code"` for both agents and equals the `usage_details.py`
   REGISTRY key (glob `dtcoder.txt`) — `calculate-cost.py` overrides `--harness`
   with `agent_info.name`, so a mismatch nulls every cost field.
4. Usage recovery from a `dtcoder.txt` `stream.usage` event: `n_input_tokens`
   carries `input_tokens - cache_write_tokens` (fresh + cache_read), `n_cache_tokens`
   the cache reads, `n_output_tokens` the output; absent log leaves them unset.
5. Pier wrapper allowlist is `["api.moonshot.cn"]`.
6. Pier environment keeps its native evidence mounts when the CA mount is added.
7. The runner preserves native rewards (1 / 0 / unscored) and refuses to
   overwrite an existing job's first attempt.
8. Usage recovery from the **OpenAI-completions** wire, where `cache_read_tokens`
   / `cache_write_tokens` come back **null** (only anthropic-messages fills them):
   a null cache field reads as 0, so `n_input`/`n_output` are still recorded
   instead of nulling the whole trial (which would score a reward-1 run
   `infra_invalid`). Ground truth from a real `dtcoder chat --json` run.
9. The model identifier handed to dtcoder (config model `name`, `agent create
   --model`, `chat --model`) is the wire id `kimi-k3`, and the harbor-facing
   `openai/kimi-k3` label never reaches dtcoder — captured from the real
   `install()`/`run()` command strings. dtcoder forwards the model `name` as the
   OpenAI wire `model`, and Moonshot 404s on `openai/kimi-k3` (verified live).

## Smoke test (real model calls, verified 2026-09-22/23)

Isolated `AGENTIX_STATE_DIR`, no Runta. Two live-key turns plus one dummy-key
replay confirmed the integration end to end against the **actual submission
endpoint** and caught two real bugs:

- The official Moonshot platform key works at `https://api.moonshot.cn/v1`
  (OpenAI-compatible, `Authorization: Bearer`, model `kimi-k3` from `GET /models`).
  Replaying this profile's exact `install()` → `start()` → `run()` command chain
  (`config apply`, `agent create fh --from primary`, `sessions create`, `chat`)
  returns `rc=0` with a real reply; the event stream uses the nested `event.name`
  discriminator this profile parses and emits `stream.usage` + `stream.profiling`.
  `--thinking-level high` resolves to OpenAI `reasoning_effort=high` on the wire.
- **Bug 1 (usage, fixed):** the OpenAI-completions wire reports
  `cache_read/cache_write` as `null` (both Moonshot and Kimi Code do this; only
  anthropic-messages fills them). The original 4-field guard in
  `populate_context_post_run` rejected the event, leaving usage `None` — a reward-1
  trial would have scored `infra_invalid`. Null cache now reads as 0 (case 8).
- **Bug 2 (wire model, fixed):** dtcoder forwards the configured model *name* as
  the OpenAI `model` param. Registering `name:"openai/kimi-k3"` and passing
  `--model openai/kimi-k3` made Moonshot return `404 Not found the model
  openai/kimi-k3` — i.e. every trial would have failed. The config `name`,
  `agent create --model` and `chat --model` now use the wire id `kimi-k3`
  (`self._provider_model`); `self.model_name` stays the harbor label only
  (case 9). The fixed chain returns `wire_model:kimi-k3`, `completed:true`, a real
  reply.

The alternative Kimi Code product (`api.kimi.com/coding/v1`, model `k3`, `sk-kimi-`
keys) was also smoke-tested and works; `provider_url` / `provider_api` /
`provider_model` are constructor kwargs, so re-pointing is configuration, not code.
Whichever endpoint ships, its `--secret-host` and egress allowlist host must match.

## Not yet validated (needs live infra)

These require a provisioned Runta runtime and are **not** covered above:

- Runta runtime → `api.moonshot.cn` connectivity. The endpoint is reachable and
  correct from a China-region test host, but that does **not** prove the Runta
  runtime's egress (region undisclosed) can reach a CN endpoint — verify with a
  `curl` from inside the runtime before any real batch.
- `dtcoder` honouring `HTTPS_PROXY` under Pier and trusting the Runta MITM CA
  (the provider crate must be built with `rustls-tls-native-roots`; never set
  `DTCODER_ROUTER_INSECURE_TLS`).
- An end-to-end trial producing a real reward and the `results/candidates/<run>/`
  evidence pack. No results are published here yet.

## Upstream fixes shipped alongside

- `scripts/usage_details.py`: adds the `"aiwork-code"` REGISTRY entry + parser.
- `scripts/generate-chart.mjs`: label placement no longer throws when a candidate
  scores ≥80% (it previously killed both the chart and the report). Proposed as a
  standalone bug fix, independent of this profile.
