"""Select the official suite runner and supply the MCode connection settings.

This is a --cmd target for the upstream run-trials.sh, whose timeout encloses
the selected runner. It does not restore runtimes, resume jobs or score results.
"""

import argparse
import json
from pathlib import Path
import signal
import subprocess
import tempfile


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
        "import_path": "mcode_kimi_profile:ConfiguredMCode"
        if runner == "harbor" else "pier_mcode:MCode",
        "model_name": model,
        "env": {
            "OPENAI_API_KEY": "runta-secret-stub",
            "OPENAI_BASE_URL": "https://api.moonshot.cn/v1",
        },
        "kwargs": {
            "version": "0.3.2",
            "bundle_path": str((root / "mcode-runtime.tar.gz").resolve()),
            "model_profile": str(root / "kimi-k3-model-settings.json"),
            "api_format": "openai-completions",
            "context_window": 1048576,
            "max_output_tokens": 131072,
        },
    }
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
            }, {
                "type": "bind",
                "source": str(jobs / "mcode-data"),
                "target": "/tmp/harbor-mcode",
            }],
            "env": {**{name: ca for name in (
                "CURL_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
                "PIP_CERT", "GIT_SSL_CAINFO", "NODE_EXTRA_CA_CERTS",
            )}, "UV_NATIVE_TLS": "1"},
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
    data_dir = args.jobs / "mcode-data"
    data_dir.mkdir(parents=True, exist_ok=False)
    data_dir.chmod(0o777)
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
