# Repairs for isolated evaluations

Use this reference when smoke tests fail before useful work, required dependencies
are unavailable offline, or the verifier fails while fetching its own inputs.
The runner examples use Harbor 0.22.0; verify version-specific details before
applying them to another setup.

## Diagnose the failing phase

Read the agent trajectory, verifier stdout, reward, and harness exception together.
Exit code zero from the runner does not establish that a task passed. Likewise,
network warnings are not the cause when the verifier actually reaches a failing
answer assertion.

- `chess-best-move`: returning one move when the verifier requires all valid mating
  moves is an incomplete answer, even if dependency setup logs network warnings.
- `build-cython-ext`: 10 checks passed, including extension compilation and function
  checks; the final check attempted a GitHub clone, then ran pytest on a missing
  directory. This is blocked verification, not evidence that the repository tests
  passed or that the agent's implementation failed.
- A pending `trial.json` with `recovery: true` is a collection/recovery marker. Check
  the durable worker before reporting it as a completed infrastructure failure.

For confirmed infrastructure failures, preserve the original trial record and raw
reward, annotate the evidence and reason, and classify the normalized attempt as
`infra_invalid`. Do not turn a partial test count into a passing reward. If the
repaired verifier reaches real assertions that fail, record an agent failure.

## Supply pinned verifier sources offline

Inspect dependency fetches inside test code as well as `test.sh`. Preinstalling pip
dependencies does not cover a test that later invokes `git clone`. Preserve the
user's isolation choice; do not widen task egress to make verifiers work.

Prefer a pinned, read-only source cache, scoped to the verifier process. For the
observed Cython task, the unmodified verifier runs:

```bash
git clone --depth 1 --branch 0.5.3 https://github.com/SPOCKnots/pyknotid.git "$destination"
```

The verified source is commit `441c807dbec2ee32e1da572e24e58d52a4eb7afa`; its `tests`
tree is `25307f3fc7c3c1688e7ad36f8b435b41e20e610e`. Prepare a bare repository from
the pinned source or a verified bundle, run `git fsck --full`, check both hashes,
and mount it read-only at `/opt/fh-verifier-git/pyknotid.git`. Record the source URL,
ref, resolved commit, bundle hash when used, and mount in the run manifest.

Harbor 0.22.0 supports verifier-only environment overrides:

```bash
--verifier-env GIT_CONFIG_COUNT=1 \
--verifier-env GIT_CONFIG_KEY_0=url.file:///opt/fh-verifier-git/pyknotid.git.insteadOf \
--verifier-env GIT_CONFIG_VALUE_0=https://github.com/SPOCKnots/pyknotid.git
```

This lets the original command clone the cached repository using Git's file
transport, which supports its shallow-clone request. Do not rewrite all GitHub
URLs, replace `git` with a fake success wrapper, change assertions, or grant these
environment overrides to the agent. Git's `insteadOf` matching uses URL prefixes;
use the full repository URL, never just the host. If verifier Git overrides already
exist, merge their indexed configuration rather than overwriting it.

Validate the exact original clone command in a disposable container with
`--network none`: assert a zero exit code, the expected HEAD and test-tree hashes,
and the presence of the tests directory. Also verify that an unrelated repository
URL cannot be fetched. This proves the download blocker is fixed; only a full task
retry or a verifier rerun against the preserved original workspace proves its score.

Keep cached verifier inputs inaccessible to the agent when they contain hidden
grading material. In this Cython case, the cached public upstream tree is already
present in the task's supplied source bundle; do not generalize that property to
other tests. Never seed a task with a repaired implementation or solution artifact.

Run the repaired attempt under a new run ID and preserve the original. Do not change
an active sweep's configuration halfway through or overwrite a shared runtime's
active job directory. Queue retries behind ongoing trials when sharing resources.
Disclose dependency provisioning and cache changes; they do not establish baseline
comparability without a matched control.

## Preflight harness capabilities

Use synthetic, non-benchmark probes before spending a full sweep: write/read a
file through native tools, run a background command and collect its result, verify
delegation if enabled, and read a synthetic image for visual tasks. A text response
from the gateway does not prove that any of these paths works.

Validate tool payloads and workspace selection against the installed CLI's schema.
Enable the provider capabilities required by the harness, including function
calling, streaming, and vision when applicable. Verify that image context reaches
the model through the selected tool mode. Record any CLI patch hash and settings,
and validate actual model requests. Do not infer tool execution from an
assistant's prose.

Subagents may continue working while CLI output is quiet. Capture thread and
subagent messages plus progress timestamps before diagnosing a stall. Preserve
raw model requests, response events, and tool results without credentials.

## Proxy and dependency preparation

When translating a verifier's `pip install` command to `uv pip install`, parse its
arguments with `shlex.split` and add required boolean flags only once. Do not blindly
prepend `--break-system-packages`: `largest-eigenval` already supplies it, and uv
0.9.5 rejects the duplicate before the agent starts. The reusable
[`uv_install_command`](scripts/dependency_commands.py) helper adds `--system` and
`--break-system-packages` once while preserving package pins, other repeated
arguments, and shell quoting. It accepts an argument list, not an arbitrary shell
script; inspect unsupported pip options or shell syntax before translating them.
Validate absent, already-present, and duplicated flags, then build the affected
image with the pinned uv version. Repeating a deterministic argument error will
not fix it. Preserve the blocked attempt and retry only after fixing preparation.

Preflight host-side worker utilities as well as container dependencies. In
particular, verify `jq` before launching workers that use it to publish completion
records; a task can finish successfully while the wrapper fails to record its exit.

Check connectivity from inside the task container, including HTTP(S) proxy handling
and CA trust. Outer runtime egress does not override an inner isolated network.
Do not silently disable certificate verification. In the observed Python 3.13
relay, the supplied Runta CA lacked an Authority Key Identifier; clearing only
`VERIFY_X509_STRICT` retained CA-chain and hostname verification. Prefer a corrected
CA when available and scope any compatibility adjustment to the affected client.

The observed gateway returned SSE even for a non-streaming request. A compatibility
relay must handle real terminal response events and propagate failures; it must not
fabricate completion. Verify the model route for helper calls as well as main calls.

Prepare declared source assets and pinned dependency packages before task isolation.
Hash them and record image digests. Do not solve or compile the requested task as
part of preparation. Recheck dependency failures against the current prompt and
image rather than assuming an old corpus revision from an error message.
