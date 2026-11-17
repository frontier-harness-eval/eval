"""Run a harness CLI that Harbor has no built-in agent for.

The suite gives each harness an `install` script (run as root), optional `files` and
a `run` script. Scripts run under `set -euo pipefail` with HARNESS_VERSION, STATE (a
scratch directory), LOGS and INSTRUCTION_FILE (the task text) set. A `files` key is a
destination path, which may use $HOME or $STATE. Its value is text (a string or a list
of lines) or else written as JSON; `${VAR}` in it takes the agent's env value. `uploads`
copies host files into the runtime before the install script.
"""

import json
import shlex
from string import Template

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template

STATE = '/tmp/harness'


def _script(lines):
    return 'set -euo pipefail\n' + '\n'.join(lines) + '\n'


class CommandAgent(BaseInstalledAgent):
    def __init__(
        self,
        *args,
        harness: str,
        install: list[str],
        run: list[str],
        files: dict | None = None,
        uploads: dict[str, str] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if not self._version:
            raise ValueError(f'{harness} needs a pinned version')
        self._harness = harness
        self._install = _script(install)
        self._run = run
        self._files = files or {}
        self._uploads = uploads or {}

    @staticmethod
    def name() -> str:
        return 'command-agent'

    def to_agent_info(self):
        return super().to_agent_info().model_copy(update={'name': self._harness})

    def _env(self) -> dict[str, str]:
        return {
            'HARNESS_VERSION': self._version,
            'STATE': STATE,
            'LOGS': self.environment_logs_dir.as_posix(),
            'INSTRUCTION_FILE': f'{STATE}/instruction.txt',
        }

    async def _write(self, environment, name: str, content: str) -> None:
        await self._upload_config_text(environment, content=content, remote_path=f'{STATE}/{name}', filename=name)

    async def install(self, environment) -> None:
        for source, target in self._uploads.items():
            await environment.upload_file(source, target)
        await self.exec_as_root(environment, f'mkdir -p {STATE} && chmod 777 {STATE}')
        await self._write(environment, 'install.sh', self._install)
        await self.exec_as_root(environment, f'bash {STATE}/install.sh', env=self._env())

    @with_prompt_template
    async def run(self, instruction, environment, context) -> None:
        await self._write(environment, 'instruction.txt', instruction)
        place = []
        for i, (target, value) in enumerate(self._files.items()):
            if isinstance(value, list) and all(isinstance(line, str) for line in value):
                value = '\n'.join(value) + '\n'
            text = value if isinstance(value, str) else json.dumps(value, indent=2)
            await self._write(environment, f'file-{i}', Template(text).safe_substitute(self._extra_env))
            place.append(f'install -D -m 600 "$STATE/file-{i}" "{target}"')
        await self._write(environment, 'run.sh', _script(place + self._run))
        logs = shlex.quote(self.environment_logs_dir.as_posix())
        # tee keeps output when the CLI fails; the script's own exit status is the run's.
        await self.exec_as_agent(
            environment,
            f'mkdir -p {logs} && bash {STATE}/run.sh </dev/null 2>{logs}/stderr.log | tee {logs}/stdout.log; '
            f'status=${{PIPESTATUS[0]}}; cat {logs}/stderr.log >&2; exit "$status"',
            env=self._env(),
        )

    def populate_context_post_run(self, context) -> None:
        pass
