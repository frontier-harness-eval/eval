# Adapters used for this run

These are the adapter files the evaluation gateway used for run
`20261014-164330-fhe-aiwork-29695-30052`. Their source has not changed since 2026-09-22, before
the run, and the instruction suffix recorded in all 30 `print.jsonl` files and the DeepSWE command
lines in `job.log` match them exactly. They are not the adapters proposed in #24, which drive dtcoder differently; #24 was not used here.

| File | Runner | Import | sha256 |
|---|---|---|---|
| `aiwork_agent.py` | Harbor 0.22.0 (Terminal-Bench) | `-a aiwork_agent:AiworkAgent` | `9371229209b80baf948209a944225500ae53cacb314993c37684ddc37a9cf2e6` |
| `aiwork_pier_agent.py` | Pier 0.3.1 (DeepSWE) | `--agent-import-path aiwork_pier_agent:AiworkAgent` | `e97a0e6fc8d384ba41ddcf6c68eb064224eec6a170daa743334aa4192279c926` |

The two published adapter files differ from the run copies only in that the internal model-gateway host, the two fallback IPs and the gateway's name are replaced with placeholders. The sha256 values above are those of the unredacted run copies; the published files hash to `be0054e23fcc5d43e8bd2e901dd2667a95743de106a305308c2bc6a2e7b8782a` (`aiwork_agent.py`) and `e5391b692e9306daf7fe614df2efca0b84e427995d42e3d9c7940c32cec32a56` (`aiwork_pier_agent.py`).

Per task they upload the dtcoder binary, point it at the model provider, and run
`dtcoder __print` once with auto-approve, writing its stream-json to `/logs/agent/print.jsonl`.
The Pier adapter fills Pier's token usage from that stream; for Terminal-Bench the gateway
reads usage from the same `print.jsonl` with the FHE `usage_details` parser. They also change the task in ways a
reviewer should know about, listed in `../run-config.json` → `harness_modifications`:

- the operating-rules block appended to every task instruction (`_RULES`);
- the uv/Python preload, used when the tarball exists on the host (`/tmp/uv-preload.tar.gz`, or the
  path in `DTCODER_UV_PRELOAD`); its contents are not published;
- `/etc/hosts` pinning of `<internal-gateway-host>` (Harbor adapter only).

Arguments used in this run: `dtcoder_bin`, `model=kimi-k3`, `thinking_level=high`,
`provider_url=https://<internal-gateway-host>/v1`, `provider_api=anthropic-messages`, and for
DeepSWE `timeout_sec=5400`. The provider key is passed as the environment variable
`AGENTIX_CONFIG_MODELS_PRIMARY_API_KEY`.

The module docstrings' remark about wire choice is the author's note at the time; some sweeps
listed in `../TRACES.md` used the openai-responses wire with other builds.

Not included: the gateway runner that launched the jobs (its settings are described in
`../run-config.json`), the uv-preload tarball, and the dtcoder binary itself.
