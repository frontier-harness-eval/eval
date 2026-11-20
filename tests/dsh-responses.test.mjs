import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const transport = readFileSync(new URL('../skills/frontierharness-eval/scripts/adapters/dsh/responses.cjs', import.meta.url), 'utf8');
const endpoint = 'https://provider.test/v3/responses';

for (const limit of ['', '2']) {
  test(`DSH preserves native tools and scopes the provider key with search limit ${limit || 'unset'}`, async () => {
    const calls = [];
    const logs = [];
    const removed = [];
    const fs = {
      readFileSync: () => 'fixture-bearer',
      unlinkSync: path => removed.push(path),
      appendFileSync: (_, entry) => logs.push(entry),
    };
    const context = vm.createContext({
      require: () => fs, Request, Headers,
      process: { env: { FH_DSH_RESPONSES_URL: endpoint, FH_DSH_WEB_SEARCH_MAX_KEYWORDS: limit } },
      fetch: async (url, init) => {
        calls.push({ url, init });
        return new Response('{}');
      },
    });
    vm.runInContext(transport, context);
    const tools = [{ type: 'function', name: 'terminal' }];
    const body = JSON.stringify({ model: 'test-model', tools });
    const init = { method: 'POST', headers: { authorization: 'Bearer placeholder' }, body };
    await context.fetch('https://other.test/v3/responses', init);
    assert.equal(calls[0].init, init);
    await context.fetch(new Request(endpoint, init));
    assert.equal(removed.length, 1);
    const sent = calls[1].init;
    assert.equal(sent.headers.get('authorization'), 'Bearer fixture-bearer');
    assert.equal(sent.redirect, 'error');
    assert.deepEqual(JSON.parse(sent.body).tools, limit ? [...tools, { type: 'web_search', max_keyword: 2 }] : tools);
    assert.equal(logs.length, 1);
    assert.ok(!logs[0].includes('fixture-bearer'));
  });
}
