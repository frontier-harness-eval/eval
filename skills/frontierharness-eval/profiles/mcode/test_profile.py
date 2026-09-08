import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import AsyncMock, Mock

import yaml
from harbor.models.agent.context import AgentContext
from harbor.models.job.config import JobConfig as HarborConfig
from pier.models.job.config import JobConfig as PierConfig
from pier.models.task.config import EnvironmentConfig
from pier.models.trial.paths import TrialPaths

from mcode_kimi_profile import ConfiguredMCode
from pier_environment import Environment
from pier_mcode import MCode
from run_task import configuration

PROFILE = Path(__file__).resolve().parent
REPO = PROFILE.parents[3]


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def agent(self, cls=ConfiguredMCode):
        return cls(logs_dir=self.root, model_name="openai/kimi-k3", version="0.3.2",
                   model_profile=PROFILE / "kimi-k3-model-settings.json",
                   context_window=1048576, max_output_tokens=131072)

    def test_all_official_tasks_parse_without_limit_or_resource_overrides(self):
        counts = {"harbor": 0, "pier": 0}
        for file in (REPO / "tasks").glob("*/task.toml"):
            suite, task = tomllib.loads(file.read_text())["task"]["name"].split("/")
            source = "terminal-bench" if suite == "terminal-bench" else "deep-swe/tasks"
            target = self.root / source / task / "task.toml"
            target.parent.mkdir(parents=True)
            target.write_text(file.read_text())
            runner, raw = configuration(self.root, suite, task, "openai/kimi-k3", self.root / "jobs")
            config = (HarborConfig if runner == "harbor" else PierConfig).model_validate(raw)
            counts[runner] += 1
            self.assertEqual(config.tasks[0].path, target.parent)
            self.assertEqual(config.n_attempts, 1)
            self.assertEqual(config.retry.max_retries, 0)
            self.assertIsNone(config.agents[0].override_timeout_sec)
            self.assertIsNone(config.verifier.override_timeout_sec)
            for key, value in config.environment.model_dump().items():
                if key.startswith("override_"):
                    self.assertIsNone(value, key)
            self.assertEqual(config.agents[0].env["OPENAI_API_KEY"], "runta-secret-stub")
        self.assertEqual(counts, {"harbor": 21, "pier": 9})

    def test_model_metadata_round_trip_preserves_other_configuration(self):
        agent = self.agent()
        agent._DATA_DIR = str(self.root)
        original = {
            "defaultModel": "existing",
            "custom_provider": {
                "harbor-openai": {
                    "apiKey": "runta-secret-stub", "baseUrl": "https://api.moonshot.cn/v1",
                    "models": {"kimi-k3": {"name": "K3"}, "other": {"name": "Keep me"}},
                },
                "other-provider": {"models": {"other": {"name": "Unchanged"}}},
            },
        }
        file = self.root / "config.yaml"
        file.write_text(yaml.safe_dump(original, sort_keys=False))
        subprocess.run(["bash", "-c", agent._build_model_limits_command(
            "harbor-openai", "openai", "kimi-k3")], check=True, capture_output=True)
        expected = json.loads(json.dumps(original))
        expected["custom_provider"]["harbor-openai"]["models"]["kimi-k3"] = json.loads(
            (PROFILE / "kimi-k3-model-settings.json").read_text())
        self.assertEqual(yaml.safe_load(file.read_text()), expected)

    def test_usage_fallback_and_missing_usage(self):
        agent = self.agent()
        context = AgentContext()
        agent.populate_context_post_run(context)
        self.assertIsNone(context.n_input_tokens)
        usage = {"inputTokens": 10, "cacheReadTokens": 20, "outputTokens": 30}
        (self.root / "mcode.jsonl").write_text("[]\n" + json.dumps({
            "type": "exec.completed", "result": {"usage": usage}}) + "\n")
        agent.populate_context_post_run(context)
        self.assertEqual((context.n_input_tokens, context.n_cache_tokens, context.n_output_tokens),
                         (30, 20, 30))

    def test_pier_preserves_native_evidence_mounts(self):
        folder = self.root / "environment"
        folder.mkdir()
        (folder / "Dockerfile").write_text("FROM ubuntu:24.04\n")
        mounts = [{"type": "bind", "source": str(self.root / "sessions"),
                   "target": "/tmp/harbor-mcode"}]
        environment = Environment(
            environment_dir=folder, environment_name="fixture", session_id="fixture",
            trial_paths=TrialPaths(trial_dir=self.root / "trial"),
            task_env_config=EnvironmentConfig(), mounts_json=mounts,
        )
        self.assertEqual(environment._mounts_json, environment._default_log_mounts() + mounts)

    def test_pier_proxy_is_scoped_to_agent_execution(self):
        agent = self.agent(MCode)
        self.assertEqual(agent.network_allowlist().domains, ["api.moonshot.cn"])
        environment = Mock()
        environment.agent_process_env.side_effect = lambda env: {
            **(env or {}), "HTTPS_PROXY": "http://fixture-proxy:8080"}
        environment.exec = AsyncMock(return_value=Mock(return_code=0, stdout="", stderr=""))
        asyncio.run(agent._mcode._exec(environment, "mcode exec 'hello'"))
        call = environment.exec.call_args.kwargs
        self.assertIn("node --require /tmp/harbor-mcode/pier-proxy.cjs", call["command"])
        self.assertEqual(call["env"]["HTTPS_PROXY"], "http://fixture-proxy:8080")
        asyncio.run(agent._mcode._exec(environment, "mcode --version"))
        self.assertNotIn("--require", environment.exec.call_args.kwargs["command"])

    def test_runner_keeps_native_rewards_and_unscored_results(self):
        task = self.root / "deep-swe/tasks/fixture"
        task.mkdir(parents=True)
        (task / "task.toml").touch()
        binary = self.root / "pier"
        binary.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
config = json.load(open(sys.argv[-1]))
folder = pathlib.Path(config['jobs_dir']) / config['job_name'] / 'trial'
folder.mkdir(parents=True)
native = json.loads(os.environ['FIXTURE_RESULT'])
(folder / 'result.json').write_text(json.dumps(native))
''')
        binary.chmod(0o755)
        for index, reward in enumerate((1, 0, None)):
            with self.subTest(reward=reward):
                native = {"verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
                          "exception_info": {"exception_type": "CancelledError"} if reward is None else None}
                jobs = self.root / f"jobs-{index}"
                command = [sys.executable, str(PROFILE / "run_task.py"), "--root", str(self.root),
                           "--suite", "datacurve", "--task", "fixture", "--model", "openai/kimi-k3",
                           "--jobs", str(jobs)]
                env = {**os.environ, "PATH": f"{self.root}:{os.environ['PATH']}",
                       "FIXTURE_RESULT": json.dumps(native)}
                subprocess.run(command, env=env, check=True, capture_output=True)
                bridge = json.loads((jobs / "result.json").read_text())
                self.assertEqual(bridge["reward"], reward)
                self.assertEqual(bridge["exception_info"], native["exception_info"])
                self.assertEqual(json.loads(Path(bridge["native_result"]).read_text()), native)
                repeat = subprocess.run(command, env=env, capture_output=True)
                self.assertNotEqual(repeat.returncode, 0)
                self.assertIn(b"preserve its first attempt", repeat.stderr)


if __name__ == "__main__":
    unittest.main()
