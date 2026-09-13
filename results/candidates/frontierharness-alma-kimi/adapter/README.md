# Running Alma on the FrontierHarness Eval

These are the files that ran the result in this directory, copied verbatim from
the Alma checkout at `a26dd7b4` (`eval/frontierharness/` and
`eval/ssh-docker-shim.sh`). They are here so anyone with access to the Alma
source can run it through the official pipeline the same way, and so the
methodology can be read rather than described. The Alma repository itself is
private at submission time; nothing here replaces it.

## What runs where

Alma is a server application, not a CLI, so it runs the other way round from
the published harnesses: the headless server (`bin/server.mjs`) lives on the
Runta runtime host next to Harbor/Pier, and each task container is attached as
an Alma **remote host**. Alma's ssh transport is pointed at
`ssh-docker-shim.sh`, which turns `ssh <container> <cmd>` into
`docker exec -i <container> sh -c <cmd>`, so every read, edit and command
happens inside the container through Alma's ordinary remote-host code path.
Model traffic goes Alma → `fw-proxy.mjs` (127.0.0.1, logs every response's
`usage` block) → `https://api.fireworks.ai`, where Runta's egress proxy swaps
the `runta-secret-stub` for the real key; the key never enters the runtime.

| file | role | lives at (in the Alma checkout) |
| --- | --- | --- |
| `install-alma.sh` | `--install-script` for `provision-golden-checkpoint.sh`: Node 22 + pnpm, builds `bin/server.mjs`, starts Alma once to write provider/eval settings into `/work/alma-data`, stops it, writes `/work/alma/alma-manifest.json` | `eval/frontierharness/` |
| `alma-drive.mjs` | REST/WebSocket driver: `ensure-server`, `configure`, `run` (remote host → workspace on `/app` → thread → the task instruction verbatim with an explicit tool list → poll → one time-check steer near the deadline → export traces and usage to `/logs/agent`), `stop-server` | `eval/frontierharness/` |
| `fw-proxy.mjs` | usage-logging proxy in front of the provider | `eval/frontierharness/` |
| `alma_fh_common.py` | container discovery, driver subprocess, cost accounting, and the `00-summary/alma-summary.json` digest | `eval/frontierharness/` |
| `alma_harbor_agent.py` | Harbor `BaseAgent` (`-a alma_harbor_agent:AlmaAgent`), Terminal-Bench suite | `eval/frontierharness/` |
| `alma_pier_agent.py` | Pier `BaseAgent` (`--agent-import-path alma_pier_agent:AlmaAgent`), DeepSWE suite | `eval/frontierharness/` |
| `run-task.sh` | the `--cmd` template for `run-trials.sh`: dispatches to Harbor or Pier with the adapter, then summarizes | `eval/frontierharness/` |
| `ssh-docker-shim.sh` | the ssh stand-in described above | `eval/` |

Things a reviewer may want to check directly in `alma-drive.mjs`: the
instruction is read from the runner's `instruction.md` and sent unchanged; the
tool list is `Bash,BashOutput,KillShell,Read,Write,Edit,Glob,Grep`
(`ALMA_FH_TOOLS` overrides it); the only other message the model ever receives
is the generic time-check steer, which carries no task information; there are
no retries.

## Running it

On the operator machine, in a clone of `frontier-harness-eval/eval` at
`e837a70` with `../eval-deviations.patch` applied (two hunks:
`--repo-bundle` for a private harness, and the `alma` entry in
`usage_details.py`):

```sh
FH=skills/frontierharness-eval/scripts
ALMA=/path/to/alma            # checkout containing eval/frontierharness/
runta secret set FIREWORKS_API_KEY --prompt
git -C $ALMA bundle create /tmp/alma.bundle main

$FH/provision-golden-checkpoint.sh \
  --runtime alma-build --checkpoint alma-golden --harness alma \
  --repo https://github.com/yetone/alma --commit $(git -C $ALMA rev-parse HEAD) \
  --repo-bundle /tmp/alma.bundle \
  --install-script $ALMA/eval/frontierharness/install-alma.sh \
  --harness-topology runtime-service \
  --deep-swe-ref 435ee89 \
  --cpus 4 --memory 8192 --disk-size-gib 100 --provider fireworks \
  --keep-runtime

$FH/run-trials.sh \
  --checkpoint alma-golden --harness alma --run-id alma-$(date +%Y%m%d) \
  --provider fireworks \
  --cmd '/work/harness/eval/frontierharness/run-task.sh {suite} {task} {model} {jobs}'

node $FH/normalize-results.mjs --run runs/alma-<date> --label Alma
node $FH/generate-chart.mjs   --run runs/alma-<date>
node $FH/build-report.mjs     --run runs/alma-<date>
```

The run in this directory used exactly this, with the official 15-host egress
allowlist unchanged (see `../run-config.json`).
