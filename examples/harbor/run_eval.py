"""Run a Harbor job from Python and summarise the results.

    PYTHONPATH=. uv run --with harbor==0.22.0 python run_eval.py
"""
import asyncio
from pathlib import Path

from harbor.job import Job
from harbor.models.job.config import DatasetConfig, JobConfig, RetryConfig
from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig


def build_config() -> JobConfig:
    return JobConfig(
        job_name="hello-sum-python",
        jobs_dir=Path("jobs"),
        n_attempts=1,
        n_concurrent_trials=2,
        retry=RetryConfig(max_retries=0),
        environment=EnvironmentConfig(type="docker"),
        agents=[
            AgentConfig(name="oracle"),
            AgentConfig(
                import_path="my_agents.my_harness:MyHarness",
                model_name="fireworks_ai/accounts/fireworks/models/kimi-k3",
                env={"FIREWORKS_API_KEY": "${FIREWORKS_API_KEY}"},
            ),
        ],
        tasks=[TaskConfig(path=Path("tasks/hello-sum"))],
        datasets=[DatasetConfig(name="terminal-bench", version="2.0", task_names=["regex-log"])],
    )


async def main() -> None:
    job = await Job.create(build_config())
    result = await job.run()

    print(f"trials: {result.n_total_trials}  errors: {result.stats.n_errored_trials}")
    for trial in result.trial_results:
        reward = (trial.verifier_result.rewards or {}).get("reward") if trial.verifier_result else None
        usage = trial.agent_result
        error = trial.exception_info.exception_type if trial.exception_info else ""
        print(
            f"{trial.agent_info.name:<12} {trial.task_name:<28} reward={reward} "
            f"in={usage.n_input_tokens if usage else None} "
            f"out={usage.n_output_tokens if usage else None} {error}"
        )


if __name__ == "__main__":
    asyncio.run(main())
