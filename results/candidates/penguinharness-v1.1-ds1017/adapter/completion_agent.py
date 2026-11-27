from pathlib import Path

from penguin_agent.agent import ASSETS, PREFIX, PenguinAgent


class ReadyPenguinAgent(PenguinAgent):
    async def install(self, environment):
        await super().install(environment)
        work = Path(__file__).resolve().parent
        await environment.upload_file(work / "ready.mjs", str(PREFIX / "ready.mjs"))
        await environment.upload_file(work / "run-ready.sh", str(PREFIX / "run.sh"))
        await self.exec_as_root(environment, command=f"chmod 755 {PREFIX}/run.sh")
