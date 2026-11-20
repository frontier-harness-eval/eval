"""Use stock pinned Codex CLI, declaring GLM capabilities and native fallback prompt."""
import json
from pathlib import Path
import toml
from harbor.agents.installed.codex import Codex as HarborCodex
from pier.agents.installed.codex import Codex as PierCodex

HERE=Path(__file__).resolve().parent


class CatalogMixin:
    async def run(self,instruction,environment,context):
        await environment.upload_file(HERE/'codex-glm-models.json','/tmp/fh-glm-models.json')
        await super().run(instruction,environment,context)


class HarborCodexGLM(CatalogMixin,HarborCodex):
    def __init__(self,*args,**kwargs):
        kwargs['config']=json.loads((HERE/'codex-glm-config.json').read_text())
        super().__init__(*args,**kwargs)


class PierCodexGLM(CatalogMixin,PierCodex):
    def __init__(self,*args,**kwargs):
        kwargs['config_toml']=toml.dumps(json.loads((HERE/'codex-glm-config.json').read_text()))
        super().__init__(*args,**kwargs)
