"""Select the official suite runner and supply the AiWork.Code (dtcoder) settings.

A --cmd target for the upstream scripts/run-trials.sh, whose timeout encloses
the selected runner. It does not restore runtimes, resume jobs or score results.

Dispatch is done here in Python (argparse), not in a shell `[ "{suite}" = ... ]`
comparison: run-trials.sh shell-quotes every --cmd placeholder individually, so
a shell string compare would test `[ "'terminal-bench'" = terminal-bench ]` and
silently mis-route every task. Passing {suite}/{task}/{model}/{jobs} as separate
argv to this script sidesteps that entirely.
"""

import argparse
import json
from pathlib import Path
import signal
import subprocess
import tempfile

PROFILE = Path(__file__).resolve().parent
_SETTINGS = json.loads((PROFILE / "aiwork-model-settings.json").read_text())
_LIMIT = _SETTINGS["limit"]


def configuration(root, suite, task, model, jobs):
    if suite not in {"terminal-bench", "datacurve"}:
        raise ValueError("Unknown official task suite")
    if Path(task).name != task or model != "openai/kimi-k3":
        raise ValueError("Expected an official task name and the Kimi K3 model")
    source = "terminal-bench" if suite == "terminal-bench" else "deep-swe/tasks"
    task_path = root / source / task
    if not (task_path / "task.toml").is_file():
        raise FileNotFoundError(task_path / "task.toml")
    runner = "harbor" if suite == "terminal-bench" else "pier"
    agent = {
        "import_path": "frontierharness_aiwork:AiworkAgent"
        if runner == "harbor" else "pier_aiwork:Aiwork",
        "model_name": model,
        # dtcoder reads the provider key from this env var (its config stores it
        # as an env reference). The stub value is rewritten to the real key on
        # egress to api.moonshot.cn by the run-trials.sh Runta secret rule.
        "env": {"AGENTIX_CONFIG_MODELS_PRIMARY_API_KEY": "runta-secret-stub"},
        "kwargs": {
            "version": "1.0",
            "bundle_path": str((root / "dtcoder").resolve()),
            "provider_url": "https://api.moonshot.cn/v1",
            "provider_api": "openai-completions",
            "provider_model": "kimi-k3",
            "thinking_level": "high",
            "context_window": _LIMIT["context"],
            "max_output_tokens": _LIMIT["output"],
        },
    }
    plugin = (root / "libagentix_ce_dtdag.so")
    if plugin.is_file():
        agent["kwargs"]["plugin_path"] = str(plugin.resolve())
    ca = "/etc/ssl/certs/runta-ca-bundle.crt"
    config = {
        "job_name": task,
        "jobs_dir": str(jobs),
        "tasks": [{"path": str(task_path)}],
        "agents": [agent],
        "n_concurrent_trials": 1,
        "n_attempts": 1,
        "retry": {"max_retries": 0},
        "environment": {
            "type": "docker",
            "delete": True,
            "mounts": [{
                "type": "bind",
                "source": "/etc/ssl/certs/ca-certificates.crt",
                "target": ca,
                "read_only": True,
            }],
            # dtcoder's provider crate uses rustls with native roots; SSL_CERT_FILE
            # points it (and curl/pip/git/node) at the Runta MITM CA bundle.
            "env": {name: ca for name in (
                "CURL_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
                "PIP_CERT", "GIT_SSL_CAINFO", "NODE_EXTRA_CA_CERTS",
            )},
        },
    }
    if runner == "pier":
        config["environment"]["import_path"] = "pier_environment:Environment"
    return runner, config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/work/frontierharness"))
    parser.add_argument("--suite", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()
    runner, config = configuration(
        args.root, args.suite, args.task, args.model, args.jobs
    )
    if args.print_config:
        print(json.dumps({"runner": runner, "config": config}, indent=2))
        return
    if (args.jobs / args.task).exists():
        raise SystemExit("This task already has a job; preserve its first attempt.")
    args.jobs.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as stream:
        json.dump(config, stream)
        config_path = stream.name
    try:
        # GNU timeout signals the whole process group. Keep this parent alive
        # while the native runner handles that signal and finishes its cleanup.
        previous = signal.signal(signal.SIGTERM, lambda *_: None)
        try:
            result = subprocess.Popen([runner, "run", "--config", config_path])
            (args.jobs / "native-process.json").write_text(json.dumps({
                "pid": result.pid, "runner": runner,
            }) + "\n")
            result.wait()
        finally:
            signal.signal(signal.SIGTERM, previous)
        records = list((args.jobs / args.task).glob("*/result.json"))
        if len(records) == 1:
            native = json.loads(records[0].read_text())
            rewards = (native.get("verifier_result") or {}).get("rewards") or {}
            # Upstream run-trials.sh reads top-level rewards. Keep the runner's
            # original result intact and expose only its official verifier value.
            record = {
                "reward": rewards.get("reward"),
                "native_result": str(records[0]),
                "exception_info": native.get("exception_info"),
            }
            target = args.jobs / "result.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, indent=2) + "\n")
            temporary.replace(target)
        raise SystemExit(result.returncode)
    finally:
        Path(config_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
