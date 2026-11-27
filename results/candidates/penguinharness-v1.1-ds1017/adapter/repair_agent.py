from pathlib import Path

from completion_agent import ReadyPenguinAgent
from penguin_agent.agent import PREFIX


class MaxDefaultRepairAgent(ReadyPenguinAgent):
    async def install(self, environment):
        await super().install(environment)
        here = Path(__file__).resolve().parent
        await environment.upload_file(here/"pin-ready.mjs",str(PREFIX/"ready.mjs"))

