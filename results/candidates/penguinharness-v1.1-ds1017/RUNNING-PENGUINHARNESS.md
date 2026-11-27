# Running PenguinHarness on FrontierHarness Eval v1.1

A step-by-step recipe for reproducing the `penguinharness-v1.1-ds1017` submission (`@prismshadow/penguin-cli@0.2.18` on `DeepSeek-V4.1-1017` across the 62-task `frontier-harness-eval/frontier-harness-eval@v1.1.0` suite).

## 1. Prerequisites

| Requirement | Version / Notes |
|---|---|
| Linux x86_64 host with Docker | Docker Engine `29.1.3` + Docker Compose `v5.0.0` (tested on Ubuntu 22.04.5 LTS, kernel `6.8.0-90-generic` x86_64). Size for `concurrency × task vCPU` and ~60 GB of Docker images. |
| Python & Harbor | Python `3.13.9` with `harbor==0.26.0` installed in a virtualenv. |
| Node.js | Node.js `24.18.0` on the host (used once to build the offline install bundle and configure the host model entry). |
| Model Provider API Key | An API key for `DeepSeek-V4.1-1017` (`penguin-go/deepseek-1017`, `deepseek/deepseek-flash`, or Baseten `deepseek-ai/DeepSeek-V4.1-Flash-1017`). |

---

## 2. Build the Offline PenguinHarness Install Bundle

Building the install bundle once on the host avoids running `npm install` or hitting `nodejs.org` inside each of the 248 task containers. Every container receives the identical checksum-verified `/opt/penguin-bench` runtime:

```bash
cd results/candidates/penguinharness-v1.1-ds1017/adapter

mkdir -p /opt/fhe-eval/cache
./make_install_bundle.sh \
  /opt/fhe-eval/cache/penguin-cli-0.2.18-node-24.18.0-linux-x86_64.tar.gz \
  0.2.18 \
  24.18.0

sha256sum /opt/fhe-eval/cache/penguin-cli-0.2.18-node-24.18.0-linux-x86_64.tar.gz
# Expected (for @prismshadow/penguin-cli@0.2.18 commit 8ffec015 + node-v24.18.0-linux-x64):
# 352ed8979bef84ff5cb010fe919ccdcb116b8a75eaa325da0be1d3979b2fe51b
```

---

## 3. Configure the Host Model Entry

`PenguinAgent` reads the requested `-m <provider>/<model_id>` entry from a host PenguinHarness data root (`$PENGUIN_HOME/default_project/.project_config.toml`) and copies only that resolved model entry into the container's throw-away data root (`/opt/penguin-bench/home/default_project/.project_config.toml`, mode `0600`, outside `/logs`).

```bash
export PENGUIN_HOME=/opt/fhe-eval/cache/penguin-host
export PENGUIN_GO_API_KEY="<your-api-key>"

node set_model_key.mjs \
  --root "$PENGUIN_HOME" \
  --project default_project \
  --provider penguin-go \
  --model-id deepseek-1017 \
  --base-url "https://<your-openai-compatible-gateway>/v1" \
  --client-type deepseek-v4 \
  --context-window 1048576 \
  --max-output 65536 \
  --key-env PENGUIN_GO_API_KEY
```

Verify that the adapter resolves the endpoint host without printing the secret key:

```bash
python3 agent_host.py -m penguin-go/deepseek-1017 --host-penguin-home "$PENGUIN_HOME"
```

---

## 4. Smoke Test on a Single Task

Run one quick task (`openssl-selfsigned-cert`) to verify Docker, Harbor, the prebuilt bundle, and trace scrubbing:

```bash
export PYTHONPATH="$PWD"

harbor run \
  -d frontier-harness-eval/frontier-harness-eval@v1.1.0 \
  -i openssl-selfsigned-cert \
  -a completion_agent:ReadyPenguinAgent \
  -m penguin-go/deepseek-1017 \
  --ak penguin_version=0.2.18 \
  --ak node_version=24.18.0 \
  --ak install_bundle=/opt/fhe-eval/cache/penguin-cli-0.2.18-node-24.18.0-linux-x86_64.tar.gz \
  --ak host_penguin_home="$PENGUIN_HOME" \
  --ak thinking=max \
  --ak max_turns=-1 \
  --ak run_timeout=unlimited \
  -k 1 -n 1 \
  --jobs-dir /opt/fhe-eval/jobs/smoke
```

Check the resulting trial folder under `/opt/fhe-eval/jobs/smoke/<job>/<trial>/`:
- `result.json`: `verifier_result.rewards.reward` (`1.0`)
- `agent/penguin-outcome.json`: `status: "completed"`, `exit_code: 0`
- `agent/penguin-cost-by-session.json`: token usage and cost
- `agent/penguin/redaction.json`: confirms zero leaked keys under `/logs/agent`
- `agent/penguin/traces/default_agent/`: full JSONL session traces

---

## 5. Running the Full 62-Task × 4-Round Evaluation

Write a Harbor job configuration (`job-v1.1-62x4.json`):

```json
{
  "job_name": "penguinharness-v1.1-ds1017-62x4",
  "jobs_dir": "/opt/fhe-eval/jobs",
  "n_attempts": 4,
  "n_concurrent_trials": 2,
  "timeout_multiplier": 1.0,
  "environment": {
    "type": "docker",
    "delete": true
  },
  "agents": [
    {
      "import_path": "repair_agent:MaxDefaultRepairAgent",
      "model_name": "penguin-go/deepseek-1017",
      "kwargs": {
        "penguin_version": "0.2.18",
        "node_version": "24.18.0",
        "install_bundle": "/opt/fhe-eval/cache/penguin-cli-0.2.18-node-24.18.0-linux-x86_64.tar.gz",
        "host_penguin_home": "/opt/fhe-eval/cache/penguin-host",
        "thinking": "max",
        "max_turns": -1,
        "run_timeout": "unlimited"
      }
    }
  ],
  "datasets": [
    {
      "name": "frontier-harness-eval/frontier-harness-eval",
      "ref": "sha256:9236400fc1a6619eb72a663445c580417be9bbbab32f816c7dff76d0a96ab24a"
    }
  ]
}
```

Start the job with `PYTHONPATH` pointing to the `adapter/` directory:

```bash
export PYTHONPATH="/path/to/results/candidates/penguinharness-v1.1-ds1017/adapter"
harbor run -c job-v1.1-62x4.json
```

---

## 6. Operational Notes for Special Tasks

1. **`bun-sourcemap-leak` Container Entrypoint**:
   The upstream `bun-sourcemap-leak` image sets `ENTRYPOINT ["docker-entrypoint.sh"]`, which requires `/usr/local/bin` in `PATH`. If Harbor fails to start the container with `executable file not found in $PATH`, pass `adapter/bun-entrypoint.json` (`{"services": {"main": {"entrypoint": ["/bin/sh", "/usr/local/bin/docker-entrypoint.sh"]}}}`) in `environment.extra_docker_compose`.
2. **Offline Verifier Dependencies (`RecoveryVerifier`)**:
   Seven tasks (`filter-js-from-html`, `fix-ocaml-gc`, `large-scale-text-editing`, `mailman`, `polyglot-c-py`, `pypi-server`, `sam-cell-seg`) run `curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh` or `uvx` at scoring time (`test.sh`). On hosts where verifier containers lack external internet access or hit rate limits on `astral.sh`/`pypi.org`, `adapter/recovery_verifier.py` injects a pinned `uv 0.9.5` + wheel cache (`verifier-deps.tar.gz`) strictly after the agent finishes and before `test.sh` runs, leaving `test.sh` and all pytest assertions 100% unmodified.
3. **Secret Scrubbing**:
   At the end of every trial, `run-ready.sh` runs `helper.mjs redact` inside the container, and `PenguinAgent.populate_context_post_run` runs a second pass on the host to guarantee that the model API key never appears in `/logs/agent`.
