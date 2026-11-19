# TRACES: what evidence exists for raven-code-dsv41-20261112

This submission exports the frozen configuration, the report and the per-task / per-attempt numeric results. The underlying execution evidence is retained on the operator's side; it is **not** attached to this pull request.

## Exported in this PR

| File | Content |
|---|---|
| `REPORT.md` | Result summary, configuration and deviations, inspected failures, environment findings |
| `run-config.json` | Harness commit, model, tools, runner, network policy, task list, deviations |
| `observed-results.json` | Per task and per attempt: score, status, agent duration, captured calls, prompt / cached-prompt / completion tokens, estimated cost; a manifest digest over the 248 outcome records |
| `TRACES.md` | This file |

Integrity: the 248 outcome records (sorted `trial / reward / exception` JSON lines) hash to `b292357478743aa07a7142c42ab468f55bda2e04d35062dcadca4a12a99864a6`. The digest was computed independently from the exported data and from the job directory and matched. The Harbor job configuration hashes to `5b7105e3eec2caa592ab0137eac69bd576ac5642deeb9c328782039b2af32606`.

## Retained locally, available to the maintainers on request

For every attempt, under `jobs/raven-62x4/2026-11-12__14-38-07/<task>/<attempt>/`:

- `agent/raven-code.log`: launcher log (model/provider line, workspace, exit code, elapsed time).
- `agent/raven-usage.jsonl`: one record per model call with timestamp, prompt / cached-prompt / completion tokens, finish reason and cost basis, plus one record per tool call with its name and timestamp.
- `agent/raven-state/`: the rendered harness configuration, the tool documentation served for that attempt, and, for attempts that ended normally, the session transcript.
- `verifier/`: `test-stdout.txt`, `ctrf.json` (per-test status and traces), `reward.txt` / `reward.json`, and for FreeCAD-style tasks the grader's detail file.

Absolute local paths, credentials and host identifiers are excluded from anything shared.

## Known gaps

- **Attempts killed at the task budget keep no session transcript.** The harness writes its transcript at the end of a turn, so these attempts retain only the user turn and the usage ledger. Their commands cannot be reconstructed.
- **No provider request/response bodies.** Token counts come from the usage ledger; prompts and completions are not exported.
- **No public archive bundle.** Unlike a full evidence release, this PR does not ship a per-task archive with hashes; the operator can produce one, subject to the data-handling approval described below.

## Privacy and policy review

- The artifacts in this PR contain no prompts, model outputs, task solutions, credentials, personal data or infrastructure identifiers; they are aggregate numerics and configuration.
- The retained evidence contains agent transcripts and verifier logs. The adapter keeps the provider key off the command line, but `run.py` renders it into `agent/raven-state/.config.rendered.*.json`, and the adapter copies that directory into the evidence area. That directory is treated as secret: it is never attached to a pull request, and any bundle made for the maintainers is scrubbed first. Publishing of the aggregate results in this PR was authorized internally.
- One attempt was cancelled by a runner-registry outage and repeated; non-passing attempts were repeated in later sessions, as stated in `run-config.json`.
