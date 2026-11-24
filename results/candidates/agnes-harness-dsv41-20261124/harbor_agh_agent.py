"""Harbor BaseAgent adapter for Agnes Harness (AGH)."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any, ClassVar

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import (
    Agent,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from harbor.utils.trajectory_utils import format_trajectory_json


AGH_BUNDLE_HOST_DIR = os.environ.get("AGH_BUNDLE_DIR", "/data/agh-eval/agh-bundle")
AGH_CONTAINER_DIR = "/opt/agh"


class AgnesHarnessAgent(BaseAgent):
    """Runs Agnes Harness (`agnes-harness`) inside a Harbor task environment."""

    SUPPORTS_ATIF: ClassVar[bool] = True

    @staticmethod
    def name() -> str:
        return "agnes-harness"

    def version(self) -> str | None:
        return os.environ.get("AGH_VERSION", "main-2a3d374d0")

    async def setup(self, environment: BaseEnvironment) -> None:
        bundle_dir = Path(AGH_BUNDLE_HOST_DIR)
        if not bundle_dir.is_dir():
            raise FileNotFoundError(f"AGH bundle directory not found: {bundle_dir}")

        await environment.upload_dir(str(bundle_dir), AGH_CONTAINER_DIR)
        res = await environment.exec(
            f"chmod +x {AGH_CONTAINER_DIR}/bin/node {AGH_CONTAINER_DIR}/dist/agnes.mjs "
            f"&& {AGH_CONTAINER_DIR}/bin/node {AGH_CONTAINER_DIR}/dist/agnes.mjs --version"
        )
        if res.return_code != 0:
            raise RuntimeError(f"AGH setup failed ({res.return_code}): {res.stderr or res.stdout}")

    def _resolve_model_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        api_key = (
            os.environ.get("AGH_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
        )
        if api_key:
            env["AGH_API_KEY"] = api_key
        if self.model_name:
            env["AGH_MODEL"] = self.model_name
        base_url = os.environ.get("AGH_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        if base_url:
            env["AGH_BASE_URL"] = base_url
        return env

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        stream_log_container = f"{self.environment_logs_dir}/agh-stream.jsonl"
        stderr_log_container = f"{self.environment_logs_dir}/agh-stderr.log"

        local_instr = self.logs_dir / "instruction.txt"
        local_instr.write_text(instruction, encoding="utf-8")
        await environment.upload_file(str(local_instr), "/tmp/agh-instruction.txt")

        model_env = self._resolve_model_env()
        setup_account_cmd = ""
        if "AGH_API_KEY" in model_env and model_env.get("AGH_MODEL"):
            setup_account_cmd = (
                f"AGH_HOME=/tmp/agh-home {AGH_CONTAINER_DIR}/bin/node {AGH_CONTAINER_DIR}/dist/agnes.mjs "
                f"daemon start --profile local-dev --data-dir /tmp/agh-home/data --workspace \"$PWD\" < /dev/null && "
                f"AGH_HOME=/tmp/agh-home AGH_ENTRY={AGH_CONTAINER_DIR}/dist/agnes.mjs "
                f"{AGH_CONTAINER_DIR}/bin/node {AGH_CONTAINER_DIR}/setup_account.mjs && "
            )

        model_flag = ""
        if self.model_name and self.model_name != "demo":
            if "AGH_API_KEY" not in model_env:
                model_flag = f"--model primary={shlex.quote(self.model_name)}"

        ephemeral_flag = "--ephemeral " if "AGH_API_KEY" not in model_env else ""
        stop_daemon_cmd = (
            f"; AGH_HOME=/tmp/agh-home {AGH_CONTAINER_DIR}/bin/node {AGH_CONTAINER_DIR}/dist/agnes.mjs "
            f"daemon stop --profile local-dev --data-dir /tmp/agh-home/data --workspace \"$PWD\" < /dev/null || true"
            if setup_account_cmd
            else ""
        )

        cmd = (
            f"rm -rf /tmp/agh-home && mkdir -m 0700 -p /tmp/agh-home {self.environment_logs_dir} && "
            f"{setup_account_cmd}"
            f"AGH_HOME=/tmp/agh-home {AGH_CONTAINER_DIR}/bin/node {AGH_CONTAINER_DIR}/dist/agnes.mjs "
            f'-p "$(cat /tmp/agh-instruction.txt)" '
            f"--mode stream-json {ephemeral_flag}--permission full-access --max-turns 100 "
            f"{model_flag} "
            f"< /dev/null > {stream_log_container} 2> {stderr_log_container}"
            f"{stop_daemon_cmd}"
        )

        local_stream = self.logs_dir / "agh-stream.jsonl"
        local_stderr = self.logs_dir / "agh-stderr.log"
        res = None
        try:
            res = await environment.exec(cmd, env=model_env)
        finally:
            if not local_stream.exists():
                try:
                    await environment.download_file(stream_log_container, str(local_stream))
                except Exception:
                    pass
            if not local_stderr.exists():
                try:
                    await environment.download_file(stderr_log_container, str(local_stderr))
                except Exception:
                    pass
            self._build_atif_trajectory(local_stream, instruction, context)

        if res is not None and res.return_code != 0 and not local_stream.exists():
            raise RuntimeError(f"AGH run failed ({res.return_code}): {res.stderr}")

    def _build_atif_trajectory(
        self,
        stream_path: Path,
        instruction: str,
        context: AgentContext,
    ) -> None:
        steps: list[Step] = [
            Step(step_id=1, source="user", message=instruction),
        ]
        session_id = self.session_id or "agh-session"
        total_in = 0
        total_out = 0
        total_usd_micros = 0

        if stream_path.exists():
            for line in stream_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if obj.get("v") == "agnes-cli-result/v1":
                    session_id = obj.get("sessionId") or session_id
                    continue

                ev = obj.get("event")
                if not isinstance(ev, dict):
                    continue
                ev_type = ev.get("type")
                data = ev.get("data") or {}

                if ev_type == "assistant/message":
                    text_parts = []
                    reasoning_parts = []
                    for c in data.get("content") or []:
                        if not isinstance(c, dict):
                            continue
                        if c.get("type") == "text" and c.get("text"):
                            text_parts.append(str(c["text"]))
                        elif c.get("type") == "thinking" and c.get("text"):
                            reasoning_parts.append(str(c["text"]))
                    steps.append(
                        Step(
                            step_id=len(steps) + 1,
                            source="agent",
                            message="\n".join(text_parts) or "[tool_use / thinking]",
                            reasoning_content="\n".join(reasoning_parts) or None,
                        )
                    )
                elif ev_type == "tool/call":
                    call_id = str(data.get("toolUseId") or f"call-{len(steps)}")
                    tool_name = str(data.get("name") or "unknown")
                    args = data.get("args") if isinstance(data.get("args"), dict) else {}
                    tc = ToolCall(tool_call_id=call_id, function_name=tool_name, arguments=args)
                    if steps and steps[-1].source == "agent":
                        steps[-1].tool_calls = [*(steps[-1].tool_calls or []), tc]
                    else:
                        steps.append(
                            Step(step_id=len(steps) + 1, source="agent", message="", tool_calls=[tc])
                        )
                elif ev_type == "tool/result":
                    call_id = str(data.get("toolUseId") or "")
                    content_str = json.dumps(data.get("result") or data, ensure_ascii=False)[:16000]
                    obs = Observation(
                        results=[ObservationResult(source_call_id=call_id or None, content=content_str)]
                    )
                    if steps and steps[-1].source == "agent":
                        if steps[-1].observation is None:
                            steps[-1].observation = obs
                        else:
                            steps[-1].observation.results.extend(obs.results)
                    else:
                        steps.append(
                            Step(step_id=len(steps) + 1, source="agent", message="", observation=obs)
                        )
                elif ev_type == "cost/ledger":
                    tokens = data.get("tokens") or {}
                    in_tok = int(tokens.get("input") or 0)
                    out_tok = int(tokens.get("output") or 0)
                    usd_micros = int((data.get("billing") or {}).get("usdMicros") or 0)
                    total_in += in_tok
                    total_out += out_tok
                    total_usd_micros += usd_micros
                    if steps and steps[-1].source == "agent":
                        steps[-1].metrics = Metrics(
                            prompt_tokens=in_tok,
                            completion_tokens=out_tok,
                            cost_usd=usd_micros / 1_000_000.0 if usd_micros else 0.0,
                        )

        cost_usd = total_usd_micros / 1_000_000.0 if total_usd_micros else 0.0
        context.n_input_tokens = total_in
        context.n_output_tokens = total_out
        context.cost_usd = cost_usd

        trajectory = Trajectory(
            session_id=session_id,
            agent=Agent(
                name=self.name(),
                version=self.version() or "main",
                model_name=self.model_name,
            ),
            steps=steps,
            final_metrics=FinalMetrics(
                total_prompt_tokens=total_in,
                total_completion_tokens=total_out,
                total_cost_usd=cost_usd,
                total_steps=len(steps),
            ),
        )
        traj_path = self.logs_dir / "trajectory.json"
        traj_path.write_text(
            format_trajectory_json(trajectory.to_json_dict()),
            encoding="utf-8",
        )
