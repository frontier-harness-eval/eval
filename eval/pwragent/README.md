# Bounded real PwrAgent paired evaluation

## Newly authorized longer-thread cohort

The user authorized a **new $500 stage starting now**, using their existing
Codex Pro authentication only. `preregistered-long-threads.json` selects three
substantial DeepSWE tasks: expression-language try/catch, JSON Schema references
and dependencies, and LaTeX multicolumn layout. Each receives one OFF/ON pair
for each exact requested model (12 cells). The published Codex/KimiK3 task costs
were roughly $10–13; they are selection evidence, not promised Sol/Astra costs.
Actual membership in the requested $3–15 range is reported. Earlier cohorts
remain separate and do not charge this new authorization.

The cohort adopts corrected driver beec8a6, has no cumulative-token cutoff, and
retains each task's original 10800-second allowance. Before dispatch, original
verifiers rejected unchanged code and accepted the reference solution in
separate containers; no-turn PwrAgent checks exercised nested-directory export.
All 12 cells completed with valid grading. A subsequent full-wire audit found
one interrupted Luna helper with no counters in the small Sol ArkType ON run;
its recorded cost is partial and a conservative uncertainty allowance remains.
The other eleven runs have complete parent/helper coverage. Each model passed
two of three tasks in both modes. Astra's three OFF baselines cost $3.52–4.07;
its paired aggregate ON cost was 0.47% higher. Sol's baselines cost $0.59–0.75,
so those results do not answer the user's requested larger-thread question.
Model outputs are not repaired.
The original DeepSWE committed-patch collector is used, so committed new files
are included and uncommitted work remains outside the official submission.

`stage5-ledger.sqlite/json` is independent of the historical ledger. It includes
explicit engineering/closeout holds, serial per-cell reservations of $90 for Sol and
$120 for Astra, and a $30 observed app-catalog cost guard with conservative
next-call headroom. Reservations are not spend. Subscription usage is priced
with the dated standard API card for comparison; no API key or fallback is used.

`usage_report.py --protocol eval/pwragent/preregistered-long-threads.json` writes
CSV, JSON, and Markdown token breakdowns. Each run separates parent, Token Miser
summary, and other helper usage: cached input, uncached input, cache writes,
output, reasoning, and nonreasoning output, with dollar components. Reasoning
is already included in output; cache writes are included in uncached input.
Raw usage-line IDs support reconciliation. Account-wide Pro usage, including
the user's concurrent work, is not attributed to this evaluation.

`preregistered-sol-workflow.json` records a separate, conditional extension:
one Sol OFF/ON pair completing six public DeepSWE features in a shared thread.
The extension was planned before the last fixed-cohort Sol results, conditional
on all three Sol OFF costs remaining below $3. All six original component
verifiers and reference solutions passed the necessary zero-model checks,
including a combined patch export and grading check. Primary correctness is
the equal-weight fraction of six verified features; complete all-feature success
is secondary. One workflow pair is the statistical unit, not six independent
trials. Both arms share the original task contents, prompts, image and limits.
The original six three-hour allowances are added together; no cumulative-token
cap is imposed. The pair shares the same new-stage $500 ledger.
`workflow_report.py` exports its separate results and token breakdowns.

Its completed OFF baseline cost $2.296652, still below the requested $3 floor.
The paired ON completed at $2.170410 (−5.50%); feature score rose from 2/6 to 3/6.
These corrected totals include native Codex compaction, which was absent from the app pricing snapshot used during selection; the OFF baseline remains below $3.
Both workflow arms have complete provider/helper counters. This is descriptive
evidence from one pair, separate from the requested price-band sample.
Before ON finished, `preregistered-final-workflow-plan.json` prospectively
selected one final larger Sol pair: all six earlier features plus six distinct
features from six more repositories. This keeps prior failures in the workload.
The new pair requires both $90 trial envelopes and all operator/helper/closeout
holds to fit the unchanged $500 ceiling. It requires original baseline/oracle
checks, combined export/grading validation, and a zero-turn sandbox/Pro check
before a final protocol and images are frozen. There is no token or spend
padding, and no repeated attempt until a target price is reached. After that
one additional pair the stage pauses for review, even if it also misses the
price band. All three current-stage cohorts remain separate.

The final twelve-feature cohort is finished and paused for review. Its OFF
parent failed with provider `serverOverloaded` after 65 minutes, independently
of the harness; the committed submission passed 6/12 feature verifiers and all
139,072 regression checks. ON completed, passed 5/12 feature verifiers and
138,874/139,072 regression checks, and cost $2.987219 including all helpers and
native compaction. OFF has $2.829932 of known partial usage and retains its full
$90 uncertainty envelope. This is not a completed causal cost pair, and neither
arm establishes the requested completed $3–15 Sol baseline. No further trial
was launched. A zero-dispatch 36-hour input validation failure is retained;
the two actual arms used the prospective 24-hour amendment in
`preregistered-final-sol-workflow-v2.json`.

`native_request_reconciliation.py` audits each native response against the
App Server request ledger. It identified three additional context-compaction
requests across sixteen trial attempts, using the exact managed source model
path and native compaction events. These requests have separate `codex_compaction`
rows; Token Miser's Luna summaries stay separate. Future execution reconciles
native requests before settling each reservation; the finished cohorts retain
their original execution-source hashes. No helper or failed-turn
uncertainty was released. The audit leaves raw outputs and grades unchanged.

The sections below retain historical cohorts and limitations.

This evaluator runs the actual PwrAgent Electron application and its managed
Codex App Server inside each task's isolated native arm64 container. It compares
exact `gpt-6.1-sol` and `gpt-6-astra`, high reasoning/default service, with Token
Miser OFF/ON. It does not emulate compression or compare against a published
leaderboard as a causal baseline.

The stage is preregistered in `preregistered-stage.json`: ten pinned public
Terminal-Bench 2.0/DeepSWE tasks, one replicate per model/flag, randomized within
task. This is a resource-feasible subset, not SWE-bench Verified. Original task
verifiers stay absent during agent execution. DeepSWE grades exported patches
in pristine containers. Every admitted attempt, including infrastructure and
model failures, is retained. No benchmark solution or task patch is published.

The separately approved harder cohort is `preregistered-hard-httpx.json`: only
four HTTPX multipart task cells, both exact models OFF/ON, two million inclusive
tokens, cumulative $500 ceiling including all earlier charges/holds. All four
cells completed and passed the hidden verifier. Further model work is paused;
the previous one-cohort authorization has been removed from the review gate.
Reports filter by cohort, so this amendment is not silently pooled with stage1.

After reviewing those results, the user requested more tests. The further
bounded cohort is `preregistered-hard-python.json`: eight cells on cattrs
partial structuring and HTTPX incremental JSON streaming, with the same exact
models/runtime/settings/limits and unchanged cumulative $500 cap. Its separate
protocol hash authorizes only that cohort; it restores the review pause afterward.
The additional worst-case trial reservations are $236 plus a $15 engineering
hold. Original verifier fractions for new and regression checks are reported
alongside binary task success, with equal task weighting. A high partial score
cannot turn an incomplete or budget-stopped agent run into task success.
All eight cells have now reached an outcome: seven completed passes and one
Astra ON evaluator IPC interruption. Its original failure stays unchanged;
read-only native pricing recovery retains the full $47 unknown-usage hold.
The exact saved unfinished code, including its separately exported new module,
passed all hidden checks in a post hoc offline diagnostic without code edits or
new model calls. This is separate from successful agent completion.

Offline protocol analysis found repeated full-history hydration during budget
polling: 1,009 `thread/read` and 1,009 `thread/turns/list` requests. Near the
interruption, a history-read sequence spanned at least 31.985 seconds, exceeding
the driver's 30-second IPC deadline. The deadline error did not name its method,
so this is strong attribution rather than a proven causal diagnosis or a
Token Miser-specific failure. The existing IPC `includeTurns:false` path skips
history hydration while still returning live-ledger pricing and pending requests;
its live parent/helper freshness must be verified before a new driver adopts it.
Future fixes should label deadline calls and persist explicitly last-observed,
non-final usage before awaiting family reads. The frozen driver and original
results are unchanged; missing final usage retains its full reservation.

The user then rejected the pilot's arbitrary cumulative-token cutoff and
requested admission based on published model task costs. The separate fresh
four-cell Cython cohort is `preregistered-cython-no-token-cap.json`. New protocols
have no default token stop or evaluator time clamp; this task keeps its published
900-second agent allowance. Exact historical protocol hashes retain their former
limits solely for reproduction. Cached input remains measured, rather than a
reason to interrupt otherwise inexpensive useful work.

[Vals' Terminal-Bench 4.0 cost table](https://www.vals.ai/benchmarks/terminal-bench-4)
reports $1.72 per test for Sol and $9.58 for Astra with Mini-SWE-agent. Its tasks,
harness and unspecified effort differ from this TB2.0 Cython fixture, so those
figures support a roughly $23 four-cell planning proxy, not an exact task quote
or causal baseline. The published KimiK3 Cython results in `results/eval-data.json`
passed in all12 harness configurations; Codex's first-cold cost is $0.4190553 and
duration389.34 seconds. No published requested-model Cython price was established.

The unchanged inclusive ceiling is $500. Fresh task reservations are $20 per Sol
and $65 per Astra, plus a $10 engineering hold; unused reservations are not spend.
Observed app-catalog cost guards are $11/$24, leaving pessimistic full-context,
maximum-output next-request/helper headroom within those envelopes. There is no
token guard. A cost/time guard outcome remains visibly budget/time-limited, not
an intrinsic model-code failure. All four fresh cells use the same guarded
settings within each model pair, then restore the review pause. Historical
Cython trials remain separate: three passed all11 original verifier checks,
while Astra ON's global install was still in progress when interrupted and its
verifier passed2/11; all four lacked completed agent outcomes.

This cohort pins driver0886647b24aaf612afdb67bf71c10f008f173707 with lightweight
parent/delegate budget reads, labeled IPC deadlines and retained explicitly
nonfinal usage snapshots. Its actual no-turn Cython sandbox preflight passed;
historical driver pins and results are unchanged.

The four fresh managed parent turns completed and each original verifier passed
11/11. Common-card costs were SolOFF0.33021770/ON0.40067496 (+21.34%) and
AstraOFF1.96473450/ON1.59570636 (-18.78%), total4.29133352USD. These are one-task
descriptive pairs, not population estimates. All four frozen drivers failed
after completion while exporting an untracked nested repository directory.
Their raw statuses and strict primary failures remain visible; separate original
provider-completion/verifier diagnostics show the code correctness result.
No model or verifier was rerun and no model code was repaired. An export-only
failure with graceful shutdown can retain complete cost coverage only when the
exact completed provider terminal and final counters match; interruptions and
budget stops keep their full uncertain reservations. This offline financial
reconciliation does not change a grade or original driver result. The fresh
batch finished and the review gate is paused again.

Future-only driverbeec8a636f1be17e76051718422393739f3df98e fixes recursive
directory export, preserving source and safe relative links while omitting Git
internals and rejecting unsafe paths. Its31 contract tests/lint passed. A native
Cython-image check reproduced the nested Git directory and verified exact
exported source bytes with zero model-turn requests. The four0886647 model runs
and their failed export statuses were not modified or repeated.

The disclosed secondary three-task rollup has Sol3/3 both modes, ON recorded
cost1.65% lower (task bootstrap interval includes zero). AstraOFF3/3 andON2/3
completion-gated, with one evaluator interruption; two unaffected model pairs
tie and the interrupted saved code passes its diagnostic. Astra's recorded
portion is13.31% lower, but full cost remains unresolved with missing usage.
`aggregate-hard-cohorts.json` is aggregation-only and cannot authorize dispatch.

## Execution and evidence

`runtime-pins.json` records the production application source, eval driver PR,
managed release and exact hashes. Stage1 used PwrAgent PR2707 at6062dd7;
the harder cohort used2c7d84bd93bb7d26698befce8f1ccbf840055ab9. Build its production image following that PR's
`apps/desktop/eval/HEADLESS.md`, then overlay the pinned eval directory. Current
pilot payload is `fh-pwragent:8655446`. Source packages live under `.eval/cache`;
each task file is checked against the preregistration before dispatch. Local
paths in the preregistration identify this execution workspace and must be
relocated explicitly for reproduction; retain all content hashes and disclose
the resulting configuration hash.

The managed Linux release requires glibc2.39. Main tasks keep their original
base image and mount a separate readonly Ubuntu2.39 glibc tree. `patchelf0.18.0`
relocates only the managed siblings' ELF interpreter/RPATH; application code is
unchanged. Original release hashes and relocated hashes are both recorded.
The pilot used unrelocated binaries on Ubuntu24; each ON/OFF pair shares its
runtime. Readonly original Codex auth is mounted as uid501, with no copy or image
layer credential. The local Docker socket is never mounted into a task.

Review found the original6062 Playwright launch silently added `--no-sandbox`.
The prior sandbox claim was incorrect and is retained as a stage1 limitation.
The harder cohort pins driver2c7d84b with explicit `chromiumSandbox:true` and
uses the [official Playwright1.63 seccomp profile](https://github.com/microsoft/playwright/blob/v1.63.0/utils/docker/seccomp_profile.json)
for scoped clone/setns/unshare namespace permissions. It uses no SYS_ADMIN,
unconfined policy or root Electron. Actual native HTTPX zero-turn preflights
passed; driver DEBUG argv and live process UID/seccomp evidence are retained.

Admission is subscription-only: the approved auth must be ChatGPT account auth
with no API-key value, and the container rejects API-key or endpoint override
environment variables before launching the agent. Actual account/read receipts
identified ChatGPT Pro for every prior task. Managed provider source selects
chatgpt.com/backend-api/codex in this mode; parent App Server replies resolve
default tier, helper usage resolves standard, and fast mode is disabled.
These prove runtime route/settings, not an upstream billing invoice.
The user's concurrent Codex activity is expected. Account-wide quota and credit
balance changes are shared observations, not evaluation-only attribution; cost
accounting uses recorded evaluation/engineering thread and turn IDs.

Run from this checkout after preparing pinned payloads/task packages:

```sh
python3 -m unittest discover -s eval/pwragent -p 'test_*.py'
python3 eval/pwragent/run_stage.py
python3 eval/pwragent/reconcile_records.py  # offline, after dispatch process stops
python3 eval/pwragent/report.py --paused
# The exact separately approved protocol; the gate rejects any other hash:
python3 eval/pwragent/run_stage.py --protocol eval/pwragent/preregistered-hard-httpx.json
python3 eval/pwragent/report.py --protocol eval/pwragent/preregistered-hard-httpx.json --paused
```

`--limit N` admits only the first N preregistered cells. `--retry-infra N` is an
explicit, evidence-checked replacement of a settled zero-dispatch infrastructure
attempt; it creates a distinct ID and retains the original. It never retries a
model result. Completed records resume without dispatch. Ambiguous state fails
closed. The audited ledger includes all overhead and conservative reservations.

Outputs are local/ignored: `.eval/records/*.json`, `.eval/stage-ledger.sqlite`,
`.eval/stage-ledger.json`, `.eval/runs/*/output/{result,ready,thread}.json`, sanitized
`rollout.jsonl`/`protocol.jsonl`, original verifier records, and
`.eval/report/{interim.json,interim.md,records.jsonl}`. Costs distinguish the app's
historical pricing from a common dated official card and conservative admission
projection. Reasoning is an output subset; cache writes are an input subset.
Helpers and retrieval calls remain separate. A pending parent price row is only
reconciled with the matching completed event and exact provider counters.

## Budget and interpretation

The inclusive approved cumulative ceiling is **$500**, including orchestration,
subscription API-equivalent usage, helper calls and retries. API credit billing
is not verified; subscription execution is not assigned zero economic cost.
There is $165 held engineering allowance, serial concurrency, conservative
next-call reservations and per-task observed stops. Stops are post-request,
not provider billing caps; reservations cover in-flight uncertainty. Final stage
completion pauses further paid/subscription eval work for explicit user review.

Report paired pass@1, exact McNemar, task bootstrap cost intervals and cost per
resolved task. With zero discordant outcomes the empirical bootstrap can be
zero-width; the report also gives the finite-sample upper bound on discordance.
Financial pairs retain infrastructure-invalid grades, with separate counts from
valid score pairs. Reported cancellation costs are partial snapshots; their
full reservations remain charged. `.eval/PAUSED_FOR_REVIEW.json` blocks every
dispatch before ledger admission, and requires explicit user review approval
before an operator clears it. The current stage also reserves $8.605102 for
separately audited Jarvis eval-only overhead; unrelated root history is excluded.
Root verifiers trust Git repositories only inside their isolated task container.
Small samples cannot establish population-level effects. An enabled flag with
zero interceptions is smoke evidence, not evidence of compression efficacy.
See `PROVENANCE.md` for instruction-protection fixes and historical auxiliary
work; standalone Codex Token Miser provenance remains unconfirmed.

The harder HTTPX cohort has one valid pair per model. Both flags passed all
122 fail-to-pass and1272 pass-to-pass tests. On the common dated default price
card, Sol ON cost $0.57445632 versus OFF $0.51689660 (+11.14%); Astra ON cost
$1.73880938 versus OFF $2.62639700 (-33.80%). All four have complete usage,
including native helpers. This single task does not establish a population
effect; a zero-width task bootstrap with n=1 carries no generalization evidence.
Stage1 remains separate: five valid score pairs per model, Sol ON3/5 versus
OFF4/5 and Astra4/5 both; cancelled usage and four invalid Git verifiers limit
its cost conclusions. Review files and sanitized receipts stay in ignored
`.eval/report` and `.eval/report-stage2-hard-httpx`, with all admitted attempts.

Validation on the current checkout and untouched base e837a70: existing Node
suite33/40 passes in both, with the same seven historical report/skill failures.
The current Python evaluator suite passes29/29. Protected instruction cases pass7/7.
