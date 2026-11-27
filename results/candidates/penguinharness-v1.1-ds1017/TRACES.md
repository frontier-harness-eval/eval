# TRACES: Evidence & Integrity Manifest for `penguinharness-v1.1-ds1017`

Unlike submissions that retain execution traces only on private operator storage, **all 248 scored trials (62 tasks × 4 rounds) for `penguinharness-v1.1-ds1017` have been secret-scrubbed, hashed, and published in full** as a downloadable GitHub Release archive alongside the structured metadata in this directory.

---

## 1. Files Included in This Pull Request

| Path | Description |
|---|---|
| `REPORT.md` | Evaluation summary, per-round breakdown, cost accounting, protocol deviations, failure analysis, and 62-task table |
| `RUNNING-PENGUINHARNESS.md` | End-to-end reproduction guide (bundle build, host model config, Harbor job spec, special-task handling) |
| `TRACES.md` | This document: archive location, SHA-256 checksums, directory layout, and redaction audit |
| `run-config.json` | Frozen harness/runner configuration, bundle digests, cost conversion formulas, and protocol deviations |
| `observed-results.json` | Complete per-task and per-attempt ledger across all 248 scored trials (including per-trial `evidence_sha256`) |
| `adapter/` | Complete Harbor adapter (`penguin_agent/`) plus runtime readiness and offline verifier extensions (`completion_agent.py`, `repair_agent.py`, `ready.mjs`, `pin-ready.mjs`, `run-ready.sh`, `recovery_verifier.py`, `bun-entrypoint.json`) |

---

## 2. Public Full-Trace Release Archive (248 Scored Trials, 5,911 Files)

The complete per-trial evidence archive is published at:

- **Release URL**: [`https://github.com/lzh368/eval/releases/tag/penguinharness-v1.1-ds1017-evidence`](https://github.com/lzh368/eval/releases/tag/penguinharness-v1.1-ds1017-evidence)

| Asset | Size (Bytes) | SHA-256 Digest |
|---|---:|---|
| `fhe-penguinharness-v1.1-ds1017-evidence.tar.gz` | `142,204,248` (142.20 MB) | `318fc8467a09398623a5862770bb22d64283953084a5a2aed120714bf9b0ca72` |
| `MANIFEST.json` | `1,199,749` | `6773c1bd42e883c3260cbced521a47ea963a2698b0555a8ca4218d49c2f7a403` |
| `observed-results.json` (in this PR) | `204,024` | `b942efc75197a42b5e41195758dd86fdca1c8b9bce05fdf57e5d9cdac9a223d9` |
| 248-trial `outcomes_sha256` | — | `d928c38654986ca33cef3cc99bf3ac95185b934dfcfbb718bc8ad931377366a8` |

### Download and Verify

```bash
# Download the release assets
curl -fLO https://github.com/lzh368/eval/releases/download/penguinharness-v1.1-ds1017-evidence/fhe-penguinharness-v1.1-ds1017-evidence.tar.gz
curl -fLO https://github.com/lzh368/eval/releases/download/penguinharness-v1.1-ds1017-evidence/MANIFEST.json
curl -fLO https://github.com/lzh368/eval/releases/download/penguinharness-v1.1-ds1017-evidence/SHA256SUMS

# Verify SHA-256 checksums
shasum -a 256 -c SHA256SUMS

# Extract the archive (extracts into trials/r1 .. trials/r4 and MANIFEST.json)
mkdir -p evidence && tar -xzf fhe-penguinharness-v1.1-ds1017-evidence.tar.gz -C evidence
```

Every single trial entry in `observed-results.json` (`tasks[*].attempts_detail[*].evidence_sha256`) matches the corresponding `trial_evidence_sha256` in `MANIFEST.json`, which is the SHA-256 over all sorted `<file_sha256>  ./<relative_path>\n` lines inside that trial directory.

---

## 3. Per-Trial Directory Layout Inside the Archive

The archive contains **248 trial directories** (`trials/r1/<task>__<id>/` through `trials/r4/<task>__<id>/`, **5,911 files**, **281,239,112 bytes** uncompressed). Each trial directory includes:

| Relative Path | Content |
|---|---|
| `result.json` | Harbor trial result: `verifier_result.rewards.reward`, `agent_result` token/cost/metadata summary, timestamps, `exception_info` |
| `config.json` / `trial.log` | Resolved Harbor trial configuration and runner execution log |
| `agent/penguin-install.json` | Installed `@prismshadow/penguin-cli` (`0.2.18`) and Node.js (`24.18.0`) versions, bundle path, and config source |
| `agent/penguin-model-list.txt` | Output of `penguin config model list` inside the container (API key masked as `<configured>`) |
| `agent/penguin-run.json` | Output of `penguin run --json` (`sessionId`, `status`, final assistant reply) |
| `agent/penguin-run.stderr` | CLI standard error stream |
| `agent/penguin-outcome.json` | Exit code, status (`completed`, `timeout`, etc.), session ID, start/finish epoch milliseconds |
| `agent/penguin-cost-by-session.json` | Exact per-session token usage (`input`, `output`, `cacheRead`, `cacheWrite`, `requests`) and provider-billed USD across the main session and any delegated subagents |
| `agent/penguin-cost-by-model.json` | Aggregated model usage for the trial |
| `agent/penguin/readiness.json` | Pre-run local server readiness and `thinkingLevel: "max"` verification (`model_requests: 0`) |
| `agent/penguin/max-turns.json` | Confirmation that `max_turns` was set to `-1` (unlimited) |
| `agent/penguin/redaction.json` | Container-side secret redaction report (`replacements: 0` across all files) |
| `agent/penguin/server.log` | Local PenguinHarness server log inside the container |
| `agent/penguin/traces/default_agent/**/*.jsonl` | Complete, turn-by-turn JSONL trajectory of the main agent and every subagent (`run_subagent`), including system instructions, reasoning/thinking blocks, tool calls (`exec_command`, `read_file`, `edit_file`, `write_file`, etc.), tool outputs, and per-turn token usage |
| `verifier/test-stdout.txt` / `test-stderr.txt` | Full pytest / verifier output |
| `verifier/ctrf.json` | Structured CTRF test report (present on 240 / 248 trials; the 8 trials without CTRF are documented below) |
| `verifier/reward.txt` | Raw verifier reward (`1.0` or `0.0`) |
| `verifier/recovery-setup.json` & `recovery-diagnostics.json` | Present on the 7 tasks using post-agent offline verifier dependency recovery (`RecoveryVerifier`) |

### Note on the 8 Scored Trials Without `verifier/ctrf.json`

- `freecad-impeller` (R1–R4) and `music-harmony` (R1–R4): The upstream `test.sh` for these two v1.1 tasks executes standalone Python test runners without `--ctrf`, writing full test output to `verifier/test-stdout.txt` and the final score (`1.0` or `0.0`) to `verifier/reward.txt` and `result.json`.

---

## 4. Privacy & Security Sanitization Audit

Before packaging `fhe-penguinharness-v1.1-ds1017-evidence.tar.gz`, an automated sanitization and verification pipeline was run across all 5,911 files:

1. **Zero API Keys / Provider Secrets**:
   - During each trial, `PenguinAgent` placed `.project_config.toml` in `/opt/penguin-bench/home` (outside `/logs`) and ran `helper.mjs redact` both in-container and post-run on the host.
   - Full-archive regex scan across all 5,911 files confirmed **0 occurrences** of the `penguin-go` API key, **0 occurrences** of `sk-[A-Za-z0-9]{20,}`, and **0 occurrences** of `ghp_` / `gho_` / `github_pat_` tokens.
2. **Host Path & Username Normalization**:
   - Evaluation host paths (`/home/<operator>/penguin-frontier-eval` and `/home/<operator>`) in `config.json`, `result.json`, `trial.log`, and `penguin-install.json` were normalized to `/opt/fhe-eval`.
   - Full-archive scan confirmed **0 occurrences** of `/home/<operator>` or `/Users/<operator>`.
3. **Host LAN IP & Local Server Claim Token Redaction**:
   - Host LAN IPv4 addresses (`192.168.*.*`) logged by Docker network diagnostics were replaced with `<REDACTED-LAN-IP>` (**0 remaining occurrences**).
   - Ephemeral container-local web claim URLs (`http://localhost:<port>/?token=...`) in `agent/penguin/server.log` and `agent/penguin/logs/penguin.log` were scrubbed to `?token=<REDACTED-LOCAL-TOKEN>`.

