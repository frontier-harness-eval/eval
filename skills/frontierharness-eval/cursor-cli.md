# Cursor CLI through Harbor and Pier

Use this profile when the harness under evaluation is
[Cursor](https://cursor.com/) driven headlessly through its CLI (`cursor-agent`). Both
runners already ship an adapter for it, named `cursor-cli` in each, so there is no agent
to register: the profile fixes the provider, hands the adapter Kimi K3 prices, and
states where a Cursor row deviates from the twelve baselines so it lands with the right
caveats.

Kimi K3 is a supported Cursor model (`--model kimi-k3`), so the benchmark's fixed-model
rule holds without a workaround.

## Where this row deviates

| | Baselines | Cursor CLI |
| --- | --- | --- |
| Model call | Harness calls the provider directly; `--provider` picks the route and key | CLI calls Cursor's backend, which calls Cursor's inference partner for Kimi K3 (Moonshot, per Cursor's pricing page). Cursor's custom-key setting is documented for chat only, not the CLI. |
| Credential | Provider key, injected by the egress proxy on the provider host | `CURSOR_API_KEY`, injected on `api2.cursor.sh` |
| Version pin | Source checkout at a commit | The installed CLI version, read back from every trial. Part of Cursor's context assembly runs on its backend and has no version. |
| Cost source | Trajectory token counts at provider list prices | Token counts from the CLI's `stream-json` result event, priced at Cursor's Kimi K3 list prices |

Same weights, so **pass rate is comparable**. Cache hit rate may differ with the
partner's prefix-cache behaviour, which `reference.md` § Cost comparability already
treats as a caveat category. `build-report.mjs` flags the provider as non-baseline
automatically because `--provider cursor` is not Fireworks.

## Prerequisites

A Cursor API key from the Cursor dashboard, on a plan that allows API-key use of the CLI.
Note which plan: Cursor lists a **Cursor Token Rate** of $0.25 per million tokens on top
of model pricing for Teams and Enterprise plans, and none for individual plans. The rate
you were billed at goes into `--cursor-token-rate` below and into the report.

```bash
FH=skills/frontierharness-eval/scripts
export RUNTA_TOKEN=rt_...
export CURSOR_API_KEY=...
```

## Provision the golden checkpoint

There is no source to clone: the adapters install `cursor-agent` inside each task
container from Cursor's installer at trial time. Pin the version you expect instead of a
commit, then confirm it after the run (below).

```bash
$FH/provision-golden-checkpoint.sh \
  --runtime fh-build-cursor \
  --checkpoint fh-golden-cursor-cli-v1 \
  --harness cursor-cli \
  --harness-version "$(cursor-agent --version 2>/dev/null || echo unknown)" \
  --provider cursor \
  --cpus 4 --memory 8192 --disk-size-gib 100 \
  --prepull-tasks tasks
```

`--provider cursor` stores `CURSOR_API_KEY` as a Runta secret stub and records
`api2.cursor.sh` as the host the key is injected on. If you restrict egress
(`reference.md` § Model and providers), allow `cursor.com` for the installer and
`api.cursor.sh`, `api2.cursor.sh`, `api3.cursor.sh` for the CLI; these are the domains
Pier's own `cursor-cli` adapter allowlists.

## Smoke-test the integration

Render the Harbor command first; it needs no credentials or runtime:

```bash
$FH/run-cursor-cli.sh --print-command
```

Then run one Terminal-Bench task and one DeepSWE task from fresh restores before
spending a full sweep:

```bash
printf '%s\n' terminal-bench/regex-log datacurve/anko-typed-variable-bindings > tasks-cursor-smoke.txt

$FH/run-cursor-cli.sh \
  --checkpoint fh-golden-cursor-cli-v1 \
  --run-id cursor-cli-smoke \
  --tasks tasks-cursor-smoke.txt
```

Check the collected `cursor-cli.txt` stream in each trial's jobs before going on. Each
line settles one of this profile's open points:

1. The `system` / `init` event has `apiKeySource: "env"` and names the Kimi K3 model.
   Anything else means the CLI did not pick the key up from the runtime.
2. The first assistant turn succeeded. The runtime holds only the stub value, and the
   egress proxy swaps it into the `Authorization` header on `api2.cursor.sh`. Whether the
   CLI authenticates with that header shape against that host is not documented, so a
   working first turn is the proof. If auth fails, the fallback is a `--cmd` that exports
   the real key into the trial runtime, which leaves the stub model and has to be stated
   in the report.
3. The `result` event carries a `usage` object with `inputTokens`, `outputTokens`,
   `cacheReadTokens`, and `cacheWriteTokens`. Both adapters parse it into token totals
   and cache-hit rate; without it the cache column is empty. Cursor's public
   `output-format` reference does not list `usage`, so which CLI versions emit it is
   something the smoke run establishes.
4. `agent_info.version` in the Harbor job is the version you passed as
   `--harness-version`.

A model response without a verifier result is not a successful smoke test.

## Run the published task set

```bash
$FH/run-cursor-cli.sh \
  --checkpoint fh-golden-cursor-cli-v1 \
  --run-id "$(date +%Y-%m-%d)-cursor-cli" \
  --cursor-token-rate 0      # 0.25 on Teams and Enterprise
```

With no `--tasks` this is the repo's `tasks/` directory, the published 30. The wrapper
runs the 21 Terminal-Bench tasks through Harbor and the 9 DeepSWE tasks through Pier
under one run id, then reports the set of `cursor-agent` versions seen. More than one
version means the run is not one configuration; rerun the odd trials.

Then score and chart it the normal way:

```bash
node $FH/normalize-results.mjs --run runs/<run-id> --label "Cursor CLI"
node $FH/generate-chart.mjs    --run runs/<run-id>
node $FH/build-report.mjs      --run runs/<run-id>
```

## Cost

Harbor's `cursor-cli` adapter has built-in rates for Cursor's own models but none for
`kimi-k3`, so the wrapper passes Cursor's listed Kimi K3 prices through the adapter's
`pricing` kwarg: $3 input, $0.30 cache read, $15 output per million, cache writes at the
input rate, each plus `--cursor-token-rate`. These match the Fireworks and Moonshot list
prices behind the baselines, so at a token rate of 0 the cost column is comparable to
the same degree as any non-Fireworks provider.

Pier's `cursor-cli` adapter has no pricing override and falls back to a LiteLLM lookup
of the bare model name, which has no entry for `kimi-k3`. The 9 DeepSWE trials therefore
carry token counts but an empty cost. Do not estimate silently: either leave
`effective_cost_per_pass` as the Terminal-Bench-only figure and say so in the report, or
join per-task cost from Cursor's usage data and state the method.

## Versioning

`harness-versions.json` rows for the baselines carry a version from `agent_info.version`.
A Cursor row carries the same, plus the run date, because the backend half of the
harness cannot be pinned. This is weaker than the other rows and is worth recording as
such rather than omitting.

## What this profile does not do

- It does not drive the Cursor desktop Agent, which honours custom keys and a base-URL
  override and could in principle hit the same Fireworks route as the baselines. If Cursor
  exposes that override in the CLI, `--provider fireworks` with `--harness cursor-cli`
  becomes the straight-peer configuration and this profile's provider caveat disappears.
- It does not bundle a pinned CLI into the checkpoint. That would make the version pin as
  strong as the baselines' commit pin; add it when the per-trial installer proves to
  drift within a run.
