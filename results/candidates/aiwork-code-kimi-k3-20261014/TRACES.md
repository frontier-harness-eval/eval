# Public execution evidence

The evidence covers all 30 tasks of run `20261014-164330-fhe-aiwork-29695-30052`, including all
five failures. Nothing was rerun for this publication.

Download the [evidence tarball, `MANIFEST.json`, and `SHA256SUMS`](https://github.com/x4vierli/eval/releases/tag/aiwork-code-kimi-k3-20261014-evidence).
The release is hosted on the submission fork to keep large archives out of the upstream Git
history.

```sh
shasum -a 256 -c SHA256SUMS
tar -xzf fhe-aiwork-code-evidence-20261014-164330.tar.gz
```

## Contents

```
candidate.json  run.json  normalize.log         # the gateway's original aggregate and run record
report/  REPORT.md chart.svg index.html measurement-notes.json   # rendered by the gateway
trials/<suite>-<task>/
  trial.json  completion.json  run.log          # per-task status, reward, tokens, pricing
  jobs/<ts>/config.json lock.json result.json job.log            # Harbor/Pier job
  jobs/<ts>/<task, may be truncated>__<id>/
    result.json  config.json  trial.log              # run leaf: verifier reward, agent_info, exceptions
    lock.json                                        # Terminal-Bench (Harbor) leaves only
    exception.txt                                    # only on the two agent timeouts
    agent/print.jsonl  print.err  POSTRUN_ls.txt     # dtcoder stream-json for the whole run
    artifacts/                                       # DeepSWE model.patch; Terminal-Bench: an empty manifest
    verifier/                                        # test stdout, ctrf.json; DeepSWE base/new reports
    agent-build-context/  egress-proxy/  docker-compose-*.json   # DeepSWE (Pier) only
```

Start with a task's `verifier/` output, then `agent/print.jsonl`: streamed reasoning and text,
tool calls and results, and the `stream.profiling` per-call token usage that cost is computed
from. The harness id in raw files is `aiwork`, the internal id of AiWork.Code (submission slug
`aiwork-code`); raw files are left as produced.

`report/` is the gateway's own rendering. Its comparison table and chart place this run next to
the published baselines; that is a display, not a rank claim, and it does not account for the
selection described below.

`MANIFEST.json` lists all 633 files with byte size and SHA256, and a digest per task
directory. That digest is `evidence_sha256` in `observed-results.json` and can be recomputed with:

```sh
cd trials/<suite>-<task> && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256
```

## Omissions and gaps

- Every `agent/dogfood/` directory is omitted: dtcoder's per-round raw request/response capture
  (about 0.8 GB). It is the only place system prompts and tool schemas are recorded, so those are
  not in this bundle. Scores come from the verifier and cost from `print.jsonl`; neither uses it.
- `terminal-bench/build-cython-ext` and `terminal-bench/gcode-to-text` were killed at the 900 s
  agent timeout before dtcoder wrote its usage summary. They have no recorded usage, and cost
  totals are lower bounds. Their `print.jsonl` up to the kill is included. Publication does not
  reconstruct missing usage.
- `report/measurement-notes.json` mentions `observed-cost-audit.json`; the gateway did not
  produce that file for this run.

## Privacy and redaction

Applied to a copy before packing. No score, token count, timing, or verifier output was changed.

- **Transport proxy**: the proxy URL (credential and host:port) in Terminal-Bench job configs,
  locks, and results is replaced with `<REDACTED-PROXY>` in 105 files. One bare
  mention of the proxy host, in an apt error line captured in `polyglot-c-py`'s `print.jsonl`,
  is replaced with `<REDACTED-PROXY-HOST>`; the port number next to it is kept.
- **Corporate domain suffixes** in the same files' `NO_PROXY` lists: four replaced with
  `<REDACTED-CORP-DOMAIN>` in 105 files.
- **Squid tokens**: each DeepSWE trial's one-time Pier egress-proxy `PROXY_TOKEN` is replaced
  with `<REDACTED-PROXY-TOKEN>` (9 files).
- **Key placeholders**: the provider key is passed by environment reference only, and the gateway
  masks it at capture time to an 11-character `sk-?****???` form (present in 141 files). After
  `*_API_KEY=` in 9 DeepSWE `lock.json` files that mask is also replaced
  with `<REDACTED>`.
- **Kept** in the evidence: the model endpoint host and its fallback IPs (named only generically in this summary); the
  evaluation service account's paths under `/home/fhe-eval/` (job directories, binary path); and
  the `user:pass@example.com` and credential-shaped strings that are the httpx and
  sanitize-git-repo tasks' own test fixtures.
- Checked after redaction: the literal proxy credential, its password, the proxy host, and every
  squid token occur 0 times; no unmasked `sk-` key, `Bearer` token, or internal IP occurs. This
  is a scoped check, not proof that no secret of any shape exists.

## All complete sweeps (selection disclosure)

This run was chosen after the fact as the highest-scoring of every complete 30-task sweep our
gateway ran on this task set (local Docker, Kimi K3, checkpoint label `local-fhe-no-runta`).
Builds, the provider wire, and in one case the provider changed over time. Times are the run-id
start (UTC+8); passed is out of completed tasks. The 2026-09-22 21:41 sweep is labelled with the internal
gateway as provider in its aggregate, but its job configs point at `api.moonshot.cn`.

| Start | dtcoder build | Provider | Wire | Passed | Infra-invalid |
|---|---|---|---|---:|---:|
| 2026-09-21 11:54 | `v1.26387.0-f9e4034` | internal gateway | (not recorded) | 21/30 | 0 |
| 2026-09-22 00:38 | `v1.26387.0-f9e4034` | internal gateway | (not recorded) | 20/30 | 0 |
| 2026-09-22 09:34 | `v1.26387.0-f9e4034` | internal gateway | (not recorded) | 22/30 | 0 |
| 2026-09-22 16:42 | `v1.26392.0-88728b7` | internal gateway | (not recorded) | 17/29 | 1 |
| 2026-09-22 21:41 | `v1.26392.0-88728b7` | Kimi official API | anthropic-messages | 21/30 | 0 |
| 2026-09-23 15:26 | `v1.26393.0-0e61b64` | internal gateway | anthropic-messages | 17/30 | 0 |
| 2026-09-23 23:19 | `v1.26393.0-b7e68db` | internal gateway | anthropic-messages | 18/30 | 0 |
| 2026-09-26 11:15 | `v1.26396.0-47bd3d0` | internal gateway | anthropic-messages | 20/30 | 0 |
| 2026-09-28 00:24 | `v1.26397.0-d7cf76c` | internal gateway | anthropic-messages | 19/30 | 0 |
| 2026-09-28 11:17 | `v1.26401.0-7cec944` | internal gateway | anthropic-messages | 19/30 | 0 |
| 2026-09-30 09:52 | `v1.26403.0-27971f2` | internal gateway | anthropic-messages | 0/30 | 0 |
| 2026-09-30 09:52 | `v1.26403.0-5e650f5` | internal gateway | anthropic-messages | 0/30 | 0 |
| 2026-10-01 09:53 | `v1.26404.0-1e92abc` | internal gateway | anthropic-messages | 0/30 | 0 |
| 2026-10-05 09:49 | `v1.26387.0-f9e4034` | internal gateway | anthropic-messages | 23/30 | 0 |
| 2026-10-05 22:07 | `v1.26411.0-38cdfac` | internal gateway | anthropic-messages | 0/30 | 0 |
| 2026-10-06 11:19 | `v1.26412.0-38cdfac` | internal gateway | openai-responses | 17/30 | 0 |
| 2026-10-09 12:20 | `v1.26415.0-844012e` | internal gateway | openai-responses | 19/30 | 0 |
| 2026-10-10 13:42 | `v1.26416.0-4b5cfdd` | internal gateway | openai-responses | 19/30 | 0 |
| 2026-10-12 11:06 | `v1.26421.0-9ea2cd8` | internal gateway | openai-responses | 18/30 | 0 |
| 2026-10-12 14:36 | `v1.26421.0-60c158c` | internal gateway | openai-responses | 20/30 | 0 |
| 2026-10-12 17:17 | `v1.26421.0-9ea2cd8` | internal gateway | anthropic-messages | 24/30 | 0 |
| 2026-10-12 17:47 | `v1.26421.0-7620b11` | internal gateway | anthropic-messages | 21/30 | 0 |
| 2026-10-12 21:01 | `v1.26421.0-5884673` | internal gateway | anthropic-messages | 21/29 | 1 |
| 2026-10-13 11:03 | `v1.26422.0-7ecb0e2` | internal gateway | anthropic-messages | 23/30 | 0 |
| 2026-10-13 18:57 | `v1.26422.0-30efd90` | internal gateway | anthropic-messages | 22/30 | 0 |
| 2026-10-14 10:51 | `v1.26423.0-5733e72` | internal gateway | anthropic-messages | 21/30 | 0 |
| 2026-10-14 16:43 | `v1.26423.0-c9b4e7d` | internal gateway | anthropic-messages | 25/30 | 0 | ← **this submission**
| 2026-10-14 21:52 | `v1.26387.0-f9e4034` | internal gateway | anthropic-messages | 20/30 | 0 |
| 2026-10-14 23:12 | `v1.26387.0-f9e4034` | internal gateway | anthropic-messages | 19/30 | 0 |
| 2026-10-15 00:23 | `v1.26423.0-a2d4fe2` | internal gateway | anthropic-messages | 22/30 | 0 |
| 2026-10-15 00:32 | `v1.26387.0-f9e4034` | internal gateway | anthropic-messages | 21/30 | 0 |
| 2026-10-15 16:00 | `v1.26387.0-f9e4034` | internal gateway | anthropic-messages | 20/30 | 0 |
| 2026-10-15 19:19 | `v1.26424.0-ff61834` | internal gateway | anthropic-messages | 17/30 | 0 |
| 2026-10-17 10:31 | `v1.26387.0-f9e4034` | internal gateway | anthropic-messages | 19/30 | 0 |
| 2026-10-17 22:48 | `v1.26387.0-f9e4034` | internal gateway | anthropic-messages | 20/30 | 0 |
| 2026-10-18 00:31 | `v1.26387.0-f9e4034` | internal gateway | anthropic-messages | 20/30 | 0 |
| 2026-10-18 20:22 | `v1.26427.0-ff61834` | internal gateway | anthropic-messages | 15/30 | 0 |

Partial, aborted, and smoke runs on the same gateway, not counted above:

| Date (UTC+8) | dtcoder build | Scope | Passed |
|---|---|---|---:|
| 2026-09-20 08:49 | `v1.26387.0-f9e4034` | Terminal-Bench only | 17/21 |
| 2026-09-20 10:07 | (not recorded) | DeepSWE only | 0/9, all infra-invalid |
| 2026-09-20 11:49 | `v1.26387.0-f9e4034` | DeepSWE only | 0/9, all infra-invalid |
| 2026-09-20 11:59 | `v1.26387.0-f9e4034` | DeepSWE only | 4/9 |
| 2026-09-20 (directory date) | `v1.26387.0-f9e4034` | smoke, 1 task | 1/1 |
| 2026-09-21 11:40 | `v1.26387.0-f9e4034` | smoke, 1 task | 1/1 |
| 2026-09-22 20:24 | `v1.26392.0-88728b7` | full scope via Kimi official API, stopped after 22 tasks | 15/22 |
| 2026-10-05 09:45 | `v1.26387.0-f9e4034` | smoke, 1 task | 1/1 |
| 2026-10-06 11:00 | `v1.26411.0-38cdfac` | smoke, 3 tasks | 2/3 |
| 2026-10-12 16:59 | `v1.26387.0-f9e4034` | smoke, 1 task | 1/1 |
