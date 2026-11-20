// rc.8 exposes its shipped presets on the web profile's session service.
// Drive that same service once inside the task container, without a browser.
import { randomUUID } from 'node:crypto';
import { writeFileSync } from 'node:fs';

export const name = 'fh-preset-runner';
export const inject = ['apiProxy', 'agents', 'sessions'];

async function run(ctx, { preset, instruction }) {
  await ctx.get('loader').await();
  const sessions = ctx.apiProxy.sessions;
  const call = async (method, payload) => {
    const { result } = await sessions[method]({ rpcId: randomUUID(), payload });
    if (!result.ok) throw new Error(result.error.message);
    return result.value;
  };
  const { sessionId, agentPreset } = await call('create', { agentPreset: preset, cwd: process.cwd() });
  if (agentPreset !== preset) throw new Error(`Requested ${preset}, session selected ${agentPreset}`);
  const agent = ctx.agents.get(sessionId);
  writeFileSync('/logs/agent/dsh-preset.json', JSON.stringify({ preset, sessionId }) + '\n');
  await call('prompt', { sessionId, mode: 'queue', content: [{ type: 'text', text: instruction }] });
  await agent.whenIdle();
  await ctx.sessions.flush(agent.session);
  const end = agent.session.events.findLast(event => event.type === 'turn/end')?.data.reason;
  if (end?.kind !== 'completed') throw new Error(end?.error?.message ?? `DSH turn ended: ${end?.kind}`);
}

export function apply(ctx, config) {
  const exit = ctx.get('appExit');
  void run(ctx, config).then(() => exit(0), error => {
    console.error(error);
    exit(1);
  });
}
