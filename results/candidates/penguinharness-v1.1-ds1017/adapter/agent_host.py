#!/usr/bin/env python3
"""Print the API host a model's requests go to, for Harbor's --allow-agent-host.

    python3 agents/agent_host.py -m <provider>/<model_id> [--host-penguin-home DIR] [--host-project-id ID]

Tasks whose agent phase has no network (DeepSWE, GDPevo) reach the model provider only through
Harbor's egress allowlist. This reads the same host PenguinHarness model entry that
PenguinAgent copies into the container (data root: --host-penguin-home, else $PENGUIN_HOME,
else ~/.penguin/data; Project: --host-project-id, else $PENGUIN_PROJECT_ID, else
default_project) and prints one line: the host of the model's base URL, which is the entry's
own, else its provider group's (`[providers.<provider>]`, PenguinHarness after 0.2.13), else,
when neither sets one, the default endpoint of the provider (for example api.deepseek.com).

    harbor run ... -a penguin_agent:PenguinAgent -m deepseek/deepseek-flash \\
        --allow-agent-host "$(python3 agents/agent_host.py -m deepseek/deepseek-flash)"

Exit status 0 with the host on stdout; 1 with a reason on stderr. The credential is never
read into the output. Needs only Python >= 3.11.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

HOST_CONFIG = Path(__file__).resolve().parent / "penguin_agent" / "host_config.py"


def _load_host_config():
    # Loaded by path: importing the penguin_agent package would import Harbor.
    spec = importlib.util.spec_from_file_location("penguin_agent_host_config", HOST_CONFIG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-m", "--model", required=True, help="<provider>/<model_id>, as passed to harbor run -m")
    parser.add_argument("--host-penguin-home", help="PenguinHarness data root (default: $PENGUIN_HOME, else ~/.penguin/data)")
    parser.add_argument("--host-project-id", help="Project id (default: $PENGUIN_PROJECT_ID, else default_project)")
    args = parser.parse_args()

    host_config = _load_host_config()
    try:
        provider, model_id = host_config.split_model_name(args.model)
        entry = host_config.read_model_entry(
            provider, model_id, args.host_penguin_home, args.host_project_id, require_key=False
        )
        print(host_config.api_host(entry))
    except host_config.HostConfigError as exc:
        print(f"agent_host.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
