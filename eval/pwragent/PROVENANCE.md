This evaluation runs real PwrAgent Electron plus the managed Codex App Server
inside each isolated Linux task container. Both requested models use high
reasoning, default service tier, and fast mode off. Within a pair only the
explicit Token Miser flag changes. Raw credentials are excluded from build
contexts, logs, task trees, artifacts, and Git. The host auth file is mounted
read only, individually, into fresh Codex state; an expired login fails closed.

The historical FrontierHarness v1.0 results used Kimi K3, Terminal-Bench 2.1 and
DeepSWE. The Terminal-Bench 2.1 repository/registry could not be resolved on
2026-10-11. Historical cohorts use available Terminal-Bench 2.0 sources at
69671fbaac6d67a7ef0dfec016cc38a64ef7a77c plus pinned public DeepSWE task packages.
This is an explicitly different task/runtime/model configuration, with no
leaderboard comparability claimed. Correctness uses the original task verifier
after the agent ends; verifier/solution packages are hidden during the turn.
Native Linux arm64 execution on Apple Silicon differs from the historical
Linux amd64 runtime. Own matched on/off pairs are the causal comparison.

Recovered auxiliary repository: https://github.com/pwrdrvr/token-miser-evals
at e5b7d8f019df6b7dc35827aaad6b6c3f0e1dc5d1. It contains a historical M4 host
pilot, three controls and two Miser runs, on GPT-5.6-Sol/high. Its README reports
38.9% higher raw median cost with Miser and every cost cell disqualified by
degenerate tool output or missing interception telemetry. Tokens are absent
from that legacy cost cohort, so it cannot be repriced reliably. Twelve host
control calibrations have no paired treatment. These are historical auxiliary
evidence, not new Sol/Astra efficacy results. The current repo's documented
adapter drives PwrAgent. The standalone Codex implementation search ended
without confirmed provenance; that architecture must not be inferred from
this repository's name.

Historical authorizations were reduced from $2500 to $250, then raised to a
cumulative $500 with review pauses between bounded cohorts. On October 12 the
user authorized a separate new $500 stage, using existing Codex Pro account
authentication only. Its ledger includes parent, helper and orchestration
usage; unused reservations are not spend. No API-key fallback or paid cloud
compute is used. Outstanding/unknown dispatch usage retains its reservation.
Runs are serial. The current stage uses pinned public DeepSWE packages; the
fixed single-task cohort and the subsequent six-feature Sol workflow have
separate preregistrations, metrics and reports. They are not silently pooled.
The six-feature workflow's OFF baseline remained below $3. Before its ON result,
one final twelve-feature Sol pair was prospectively selected under the same
authorization and ceiling. It retains all earlier features and adds six distinct
repositories. After that additional pair, review is required before expansion,
regardless of whether the resulting cost falls in the requested price band.

## Protected instruction provenance

These trials use real PwrAgent, not a standalone Codex Token Miser wrapper. Production source 07055d7adf7d6845721d572c663553e7dc4102d6 includes e470e46d283fbc6a6417c0f0bf0650c98d3fb1aa (PR2470, October2 protected instruction/source output) and ab5727c9b269d1c51fbf2999fc59681e6df738f9 (PR2520, October3 exact grouped members); ancestry was verified. The mandatory instruction policy covers AGENTS.md, CLAUDE.md, SKILL.md and companion guidance. With exact per-member capture, protected text passes unchanged while eligible search output may be summarized; missing/partial capture preserves the mixed result. Protected contents are excluded from the summary prompt.

Seven focused cases from apps/desktop/src/main/__tests__/token-miser-service.test.ts passed in the actual native arm64 payload image on October11. Cases cover mandatory Code Mode instruction reads, mixed script/partly captured groups, exact protected/source members alongside search, and helper-failure/insufficient-budget fallback. Local log: .eval/protected-instruction-tests.log. This is a regression check of the shipped policy, not evidence that benchmark tasks exercised protected reads; task traces are reported separately.
