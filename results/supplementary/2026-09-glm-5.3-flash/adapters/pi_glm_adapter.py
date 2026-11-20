"""Pinned native Pi CLI control with explicit GLM capability metadata.

This is a Chat Completions control, not the unpublished Pi Responses adapter.
Only installation, model configuration, evidence collection, and runner wiring
are supplied here; Pi's prompts, tools, and agent loop remain stock.
"""
import json
import shlex

from harbor.agents.installed.pi import Pi as HarborPi
from pier.agents.installed.base import BaseInstalledAgent, with_prompt_template
from pier.models.agent.install import AgentInstallSpec, InstallStep
from pier.models.agent.network import NetworkAllowlist


def model_config():
    return {'providers': {'harbor-endpoint': {
        'baseUrl': 'https://open.bigmodel.cn/api/coding/paas/v4',
        'apiKey': '$OPENAI_API_KEY', 'api': 'openai-completions',
        'models': [{
            'id': 'glm-5.3-flash', 'name': 'GLM-5.3-Flash',
            'reasoning': True, 'input': ['text', 'image'],
            'contextWindow': 1000000, 'maxTokens': 32000,
            'thinkingLevelMap': {'off':None, 'minimal':None, 'low':'low', 'medium':None, 'high':'high', 'xhigh':'max'},
            'compat': {'thinkingFormat':'zai', 'supportsReasoningEffort':True,
                       'supportsDeveloperRole':False, 'supportsStore':False,
                       'maxTokensField':'max_tokens', 'zaiToolStream':True},
        }],
    }}}


def responses_model_config():
    cfg=model_config()
    provider=cfg['providers']['harbor-endpoint']
    provider.update(baseUrl='https://open.bigmodel.cn/api/v1',api='openai-responses')
    provider['models'][0].pop('compat',None)
    return cfg


class HarborPiGLM(HarborPi):
    def _build_custom_models_json(self, access, model_id):
        if model_id != 'glm-5.3-flash':
            raise ValueError('This control is pinned to glm-5.3-flash')
        return model_config()


class HarborPiResponsesGLM(HarborPi):
    def _build_custom_models_json(self,access,model_id):
        if model_id!='glm-5.3-flash':raise ValueError('Model pinned')
        return responses_model_config()


class PierPiGLM(BaseInstalledAgent):
    _OUTPUT_FILENAME = 'pi.txt'
    model_config=staticmethod(model_config)

    @staticmethod
    def name():
        return 'pi-glm-chat'

    def get_version_command(self):
        return '. ~/.nvm/nvm.sh; pi --version'

    def install_spec(self):
        if self._version != '0.84.2':
            raise ValueError('Control version must be 0.84.2')
        return AgentInstallSpec(
            agent_name=self.name(), version=self._version,
            steps=[
                InstallStep(user='root', env={'DEBIAN_FRONTEND':'noninteractive'},
                            run='apt-get update && apt-get install -y curl'),
                InstallStep(user='agent', run=(
                    'set -euo pipefail; '
                    'curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash && '
                    'export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" && '
                    'nvm install 22 && npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.84.2 && pi --version'
                )),
            ], verification_command=self.get_version_command(),
        )

    def network_allowlist(self):
        return NetworkAllowlist(domains=['open.bigmodel.cn'])

    @with_prompt_template
    async def run(self, instruction, environment, context):
        config = shlex.quote(json.dumps(self.model_config()))
        await self.exec_as_agent(environment, command=f'mkdir -p /tmp/pi-glm; printf %s {config} > /tmp/pi-glm/models.json')
        env = self.build_process_env()
        env['PI_CODING_AGENT_DIR'] = '/tmp/pi-glm'
        await self.exec_as_agent(environment, env=env, command=(
            'set -o pipefail; . ~/.nvm/nvm.sh; '
            'pi --print --mode json --provider harbor-endpoint --model glm-5.3-flash --thinking xhigh '
            '--session-dir /logs/agent/pi/sessions '
            f'{shlex.quote(instruction)} 2>&1 </dev/null | '
            'grep -v \'"type":"message_update"\' | stdbuf -oL tee /logs/agent/pi.txt'
        ))

    def populate_context_post_run(self, context):
        # Both context contracts expose these usage fields; use the pinned Pi parser.
        HarborPi.populate_context_post_run(self, context)


class PierPiResponsesGLM(PierPiGLM):
    model_config=staticmethod(responses_model_config)

    @staticmethod
    def name():
        return 'pi-glm-responses'
