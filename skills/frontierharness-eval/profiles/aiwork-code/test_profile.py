"""Offline tests for the AiWork.Code (dtcoder / Kimi K3) FrontierHarness profile.

No model call, no container, no Runta: task.toml round-trips against the real
Harbor/Pier JobConfig models, usage is recovered from a dtcoder event stream,
the Pier wrapper's allowlist and mount handling are checked, and the runner is
driven end-to-end with a fake native runner binary.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from harbor.models.agent.context import AgentContext
from harbor.models.job.config import JobConfig as HarborConfig
from pier.models.job.config import JobConfig as PierConfig
from pier.models.task.config import EnvironmentConfig
from pier.models.trial.paths import TrialPaths

from frontierharness_aiwork import AiworkAgent
from pier_environment import Environment
from pier_aiwork import Aiwork
from run_task import configuration

PROFILE = Path(__file__).resolve().parent
REPO = PROFILE.parents[3]
SETTINGS = json.loads((PROFILE / "aiwork-model-settings.json").read_text())

# From a real dtcoder --json run (stream.usage aggregate): input_tokens is the
# FULL prompt (fresh + cache_read + cache_write).
_USAGE = {"input_tokens": 212181, "output_tokens": 12203, "total_tokens": 224384,
          "cache_read_tokens": 93083, "cache_write_tokens": 118854}

# From a real Kimi K3 `dtcoder chat --json` run over the OpenAI-completions wire
# (Kimi Code / the live Moonshot endpoint): cache_read/cache_write come back
# null, not integers. anthropic-messages is the only wire that fills them.
_USAGE_NULL_CACHE = {"input_tokens": 3662, "output_tokens": 23, "total_tokens": 3685,
                     "cache_read_tokens": None, "cache_write_tokens": None,
                     "cache_usage_source": None}


def _usage_line(data):
    return json.dumps({"kind": "event", "category": "agent", "operation": "chat.send",
                       "event": {"name": "stream.usage", "phase": "info"}, "data": data})


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def agent(self):
        return AiworkAgent(logs_dir=self.root, model_name="openai/kimi-k3", version="1.0",
                           bundle_path=str(self.root / "dtcoder"),
                           context_window=SETTINGS["limit"]["context"],
                           max_output_tokens=SETTINGS["limit"]["output"])

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
            self.assertEqual(
                config.agents[0].env["AGENTIX_CONFIG_MODELS_PRIMARY_API_KEY"],
                "runta-secret-stub")
        self.assertEqual(counts, {"harbor": 21, "pier": 9})

    def test_limits_come_from_the_model_settings(self):
        # The K3 model settings file is the single source of truth for the
        # context/output limits the runner passes as agent kwargs.
        self.assertEqual(SETTINGS["limit"], {"context": 1048576, "output": 131072})
        agent = self.agent()
        self.assertEqual(agent._context_window, SETTINGS["limit"]["context"])
        self.assertEqual(agent._max_output_tokens, SETTINGS["limit"]["output"])

    def test_name_matches_usage_details_registry_key(self):
        # calculate-cost.py overrides --harness with agent_info.name; if the
        # REGISTRY key and name() disagree, every cost field is null.
        sys.path.insert(0, str(REPO / "skills/frontierharness-eval/scripts"))
        import usage_details
        self.assertEqual(AiworkAgent.name(), "aiwork-code")
        self.assertEqual(Aiwork.name(), "aiwork-code")
        self.assertIn(AiworkAgent.name(), usage_details.REGISTRY)
        glob, _ = usage_details.REGISTRY[AiworkAgent.name()]
        self.assertEqual(glob, "dtcoder.txt")

    def test_usage_populate_and_missing(self):
        agent = self.agent()
        context = AgentContext()
        agent.populate_context_post_run(context)
        self.assertIsNone(context.n_input_tokens)  # no dtcoder.txt yet
        (self.root / "dtcoder.txt").write_text(
            '{"event":{"name":"stream.started"}}\n'
            'non-json stderr line from tee 2>&1\n' + _usage_line(_USAGE) + "\n")
        agent.populate_context_post_run(context)
        # n_input carries fresh + cache_read (input - cache_write); price_usage
        # then derives fresh correctly. cache-write premium is an accepted lower bound.
        self.assertEqual(context.n_input_tokens, 212181 - 118854)  # 93327
        self.assertEqual(context.n_cache_tokens, 93083)
        self.assertEqual(context.n_output_tokens, 12203)

    def test_usage_populate_null_cache_from_openai_completions(self):
        # A real Kimi K3 dtcoder run over the openai-completions wire returns
        # cache_read/cache_write = null. The old 4-field guard rejected the whole
        # event, nulling usage and scoring a reward-1 trial infra_invalid. Null
        # cache must read as 0 so input/output usage is still recorded.
        agent = self.agent()
        context = AgentContext()
        (self.root / "dtcoder.txt").write_text(_usage_line(_USAGE_NULL_CACHE) + "\n")
        agent.populate_context_post_run(context)
        self.assertEqual(context.n_input_tokens, 3662)
        self.assertEqual(context.n_cache_tokens, 0)
        self.assertEqual(context.n_output_tokens, 23)

    def test_dtcoder_receives_wire_model_id_not_harbor_label(self):
        # dtcoder forwards the configured model *name* as the OpenAI wire `model`
        # param. Moonshot 404s on "openai/kimi-k3" ("Not found the model ...")
        # and only accepts "kimi-k3" — verified against the live endpoint. So the
        # config model name, `agent create --model` and `chat --model` must all be
        # the wire id (self._provider_model); self.model_name stays the harbor
        # label only. If the harbor label leaks to dtcoder, every trial 404s.
        import asyncio
        agent = self.agent()
        (self.root / "dtcoder").write_text("#!/bin/sh\n")  # install()'s is_file check
        commands = []

        async def _record(environment, command, env=None):
            commands.append(command)

        agent.exec_as_root = _record  # shadow the bound method to capture commands

        class _Env:
            async def upload_file(self, *args, **kwargs):
                return None

        asyncio.run(agent.install(_Env()))
        run_fn = getattr(type(agent).run, "__wrapped__", None)  # bypass prompt template
        if run_fn is not None:
            asyncio.run(run_fn(agent, "solve the task", _Env(), AgentContext()))
        else:
            asyncio.run(agent.run("solve the task", _Env(), AgentContext()))
        blob = "\n".join(commands)
        self.assertIn('"name":"kimi-k3"', blob)
        self.assertIn("--model kimi-k3", blob)
        # the harbor label must never reach dtcoder as a model identifier
        self.assertNotIn("openai/kimi-k3", blob)
        # ...but it stays the harbor-facing label for FrontierHarness reporting
        self.assertEqual(agent.model_name, "openai/kimi-k3")
        self.assertEqual(agent._provider_model, "kimi-k3")

    def test_pier_wrapper_allowlist_and_names(self):
        agent = Aiwork(logs_dir=self.root, model_name="openai/kimi-k3", version="1.0",
                       bundle_path=str(self.root / "dtcoder"))
        self.assertEqual(agent.network_allowlist().domains, ["api.moonshot.cn"])
        self.assertEqual(agent.name(), "aiwork-code")

    def test_pier_preserves_native_evidence_mounts(self):
        folder = self.root / "environment"
        folder.mkdir()
        (folder / "Dockerfile").write_text("FROM ubuntu:24.04\n")
        mounts = [{"type": "bind", "source": str(self.root / "ca"),
                   "target": "/etc/ssl/certs/runta-ca-bundle.crt", "read_only": True}]
        environment = Environment(
            environment_dir=folder, environment_name="fixture", session_id="fixture",
            trial_paths=TrialPaths(trial_dir=self.root / "trial"),
            task_env_config=EnvironmentConfig(), mounts_json=mounts,
        )
        self.assertEqual(environment._mounts_json, environment._default_log_mounts() + mounts)

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
    unittest.main(verbosity=2)
