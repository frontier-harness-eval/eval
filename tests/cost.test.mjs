import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const scripts = resolve('skills/frontierharness-eval/scripts');
function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'fh-cost-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const write = (path, value) => {
    mkdirSync(resolve(root, path, '..'), { recursive: true });
    writeFileSync(join(root, path), typeof value === 'string' ? value : JSON.stringify(value));
  };
  const calculate = () => {
    const result = spawnSync('python3', [join(scripts, 'calculate-cost.py'), '--trial', root,
      '--model', 'fireworks_ai/accounts/fireworks/models/kimi-k3', '--harness', 'pi-responses'], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(result.stdout);
  };
  return { root, write, calculate };
}

test('prices token classes once, removes only first-call warmth, ignores job aggregate', t => {
  const f = fixture(t);
  f.write('jobs/job/result.json', { total_cost_usd: 999 });
  f.write('jobs/job/trial/result.json', { agent_result: {
    n_input_tokens: 10000, n_cache_tokens: 6000, n_cache_write_tokens: 1000,
    n_output_tokens: 500, cost_usd: 999,
  } });
  f.write('jobs/job/trial/agent/pi.txt', [
    { type: 'message_end', message: { role: 'assistant', usage: { input: 1000, cacheRead: 2000, output: 200 } } },
    { type: 'message_end', message: { role: 'assistant', usage: { input: 3000, cacheRead: 4000, output: 300 } } },
  ].map(JSON.stringify).join('\n'));
  const row = f.calculate();
  assert.ok(Math.abs(row.cost_usd - 0.0213) < 1e-12);
  assert.ok(Math.abs(row.cost_first_cold_usd - 0.0267) < 1e-12);
  assert.equal(row.cache_hit_rate_normalized, 0.4);
  assert.equal(row.turns, 2);
  assert.equal(row.cost_source, 'price_table');
  assert.equal(row.reported_cost_usd, 999);
});

test('zero first-call cache is known; missing details and unknown models remain unknown', t => {
  const f = fixture(t);
  f.write('jobs/trial/result.json', { agent_result: { n_input_tokens: 100, n_output_tokens: 10 } });
  assert.equal(f.calculate().cost_first_cold_usd, null);
  f.write('jobs/trial/agent/pi.txt', JSON.stringify({ type: 'message_end', message: {
    role: 'assistant', usage: { input: 100, output: 10, cacheRead: 0 },
  } }));
  const row = f.calculate();
  assert.equal(row.cost_first_cold_usd, row.cost_usd);
  assert.equal(row.cache_hit_rate_normalized, 0);
  f.write('jobs/trial/result.json', { agent_info: { model_info: { name: 'other-model' } },
    agent_result: { n_input_tokens: 100, n_output_tokens: 10, cost_usd: 1 } });
  assert.equal(f.calculate().cost_usd, 1);
  assert.equal(f.calculate().cost_first_cold_usd, null);
});

test('ambiguous attempts are never summed or selected by cost', t => {
  const f = fixture(t);
  for (const id of ['a', 'b']) f.write(`jobs/${id}/result.json`, { cost_usd: 1 });
  assert.equal(f.calculate().cost_usd, null);
});

test('success-only cost coverage is separate from effective cost coverage', t => {
  const f = fixture(t);
  f.write('run.json', { harness: 'test', model: 'k3' });
  f.write('benchmark.json', { task_count: 4, task_ids: ["a", "b", "c", "d"] });
  for (const [id, success, cost] of [['a', true, 2], ['b', false, 4], ['c', false, null]]) {
    f.write(`trials/${id}/trial.json`, { id, status: success ? 'success' : 'failure', success, cost_first_cold_usd: cost });
  }
  const run = () => {
    const result = spawnSync(process.execPath, [join(scripts, 'normalize-results.mjs'), '--run', f.root,
      '--benchmark', join(f.root, 'benchmark.json')], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(readFileSync(join(f.root, 'candidate.json')));
  };
  let row = run();
  assert.equal(row.cost_per_success_normalized, 2);
  assert.equal(row.median_cost_per_success_normalized, 2);
  assert.equal(row.effective_cost_per_pass, 6);
  assert.equal(row.cost_coverage, 1);
  assert.equal(row.effective_cost_coverage, 2 / 4);
  f.write('trials/d/trial.json', { id: 'd', success: true, status: 'success', cost_first_cold_usd: null });
  row = run();
  assert.equal(row.cost_per_success_normalized, null);
  assert.equal(row.median_cost_per_success_normalized, null);
  assert.equal(row.cost_coverage, 0.5);
});

test('normalizing retained evidence corrects old reported costs without rewriting trials', t => {
  const f = fixture(t);
  f.write('run.json', { harness: 'pi-responses', model: 'k3' });
  f.write('benchmark.json', { task_count: 1, task_ids: ["a"] });
  const trial = { id: 'a', success: true, status: 'success', cost_first_cold_usd: 999 };
  f.write('trials/a/trial.json', trial);
  f.write('trials/a/jobs/attempt/result.json', { verifier_result: { rewards: { reward: 1 } }, agent_result: { n_input_tokens: 100, n_output_tokens: 10 } });
  f.write('trials/a/jobs/attempt/agent/pi.txt', JSON.stringify({ type: 'message_end',
    message: { role: 'assistant', usage: { input: 100, output: 10 } } }));
  const result = spawnSync(process.execPath, [join(scripts, 'normalize-results.mjs'), '--run', f.root,
    '--benchmark', join(f.root, 'benchmark.json')], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  const candidate = JSON.parse(readFileSync(join(f.root, 'candidate.json')));
  assert.equal(candidate.cost_per_success_normalized, 0.00045);
  assert.deepEqual(JSON.parse(readFileSync(join(f.root, 'trials/a/trial.json'))), trial);
});

test('scoring matches baseline evidence and timeout precedence', t => {
  const f = fixture(t);
  const run = () => {
    const result = spawnSync('python3', [join(scripts, 'calculate-cost.py'), '--trial', f.root,
      '--model', 'k3', '--harness', 'pi-responses', '--score'], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(result.stdout);
  };
  const started = { started_at: '2026-09-05T00:00:00Z' };
  for (const [raw, completion, status] of [
    [{ agent_setup: started, exception_info: { exception_type: 'RuntimeError' } }, {}, 'infra_invalid'],
    [{ verifier_result: { rewards: { reward: 1 } } }, {}, 'infra_invalid'],
    [{ agent_execution: started }, { exit_code: 124, timeout_seconds: 60 }, 'failure'],
    [{ agent_setup: started }, { exit_code: 124, timeout_seconds: 60 }, 'infra_invalid'],
    [{ agent_execution: started, agent_result: { n_input_tokens: 100 }, verifier_result: { rewards: { reward: 1 } }, exception_info: { exception_type: 'AgentTimeoutError' } }, { exit_code: 124, timeout_seconds: 60 }, 'success'],
    [{ agent_result: { n_input_tokens: 100 }, verifier_result: { rewards: { a: 0, b: 1 } } }, {}, 'failure'],
  ]) {
    f.write('jobs/trial/result.json', raw);
    f.write('completion.json', completion);
    const row = run();
    assert.equal(row.status, status, JSON.stringify(raw));
    assert.equal(row.success, status === 'success');
    if (status === 'success') {
      assert.equal(row.completed_with_agent_exception, true);
      assert.equal(row.duration_seconds, 60);
    }
  }
});

test('canonical manifest selection and success coverage match baseline aggregation', t => {
  const f = fixture(t);
  f.write('run.json', { harness: 'test', model: 'k3', methodology_comparable: false });
  f.write('benchmark.json', { task_count: 3, task_ids: ['a', 'b', 'c'] });
  const add = (folder, row) => f.write(`trials/${folder}/trial.json`, row);
  const success = { status: 'success', success: true, cost_first_cold_usd: 2,
    duration_seconds: 10, turns: 2, input_tokens: 100, output_tokens: 10,
    cached_input_tokens: 80, first_turn_cached_tokens: 20 };
  add('a-invalid', { id: 'a', status: 'infra_invalid', started_at: '0' });
  add('a-first', { ...success, id: 'a', started_at: '1' });
  add('a-retry', { ...success, id: 'a', started_at: '2', cost_first_cold_usd: 999 });
  add('b', { id: 'b', status: 'failure', success: false, cost_first_cold_usd: 4 });
  add('c-warm', { ...success, id: 'c', label: 'formal-warm' });
  add('c-smoke', { ...success, id: 'c', label: 'smoke-test' });
  add('c-retry', { ...success, id: 'c', attempt: 2 });
  add('unknown', { ...success, id: 'other' });
  const run = () => {
    const result = spawnSync(process.execPath, [join(scripts, 'normalize-results.mjs'), '--run', f.root,
      '--benchmark', join(f.root, 'benchmark.json')], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(readFileSync(join(f.root, 'candidate.json')));
  };
  let row = run();
  assert.equal(row.completed, 2);
  assert.equal(row.full_coverage, false);
  assert.equal(row.task_details.length, 3);
  assert.equal(row.task_details[2].status, 'missing');
  assert.equal(row.duration_coverage, 1, 'failed cells do not lower success metric coverage');
  assert.equal(row.effective_cost_per_pass, 6);
  assert.equal(row.cache_hit_rate_normalized, 0.6);
  add('c', { ...success, id: 'c', duration_seconds: null, turns: null,
    input_tokens: null, output_tokens: null, first_turn_cached_tokens: null });
  row = run();
  for (const key of ['median_duration_seconds', 'mean_turns', 'cache_hit_rate_typical', 'cache_hit_rate_normalized', 'mean_input_tokens', 'mean_output_tokens']) assert.equal(row[key], null, key);
  assert.equal(row.duration_coverage, 0.5);
  assert.equal(row.valid_coverage, 1);
  assert.equal(row.success_rate_expected, 2 / 3);
  add('c', { ...success, id: 'c', input_tokens: 300, cached_input_tokens: 300, first_turn_cached_tokens: 0 });
  row = run();
  assert.equal(row.cache_hit_rate_normalized, 0.9, 'cache aggregate is token weighted');
  assert.equal(row.cache_hit_rate_typical, 0.8, 'typical cache is the per-task median');
  assert.equal(row.cache_hit_rate_typical_q1, 0.7);
});

test('matches frozen baseline collector outputs across 36 evidence combinations', t => {
  const f = fixture(t);
  const cases = JSON.parse(readFileSync(resolve('tests/fixtures/baseline-scoring.json'))).cases;
  for (const { raw, expected } of cases) {
    f.write('jobs/trial/result.json', raw);
    const result = spawnSync('python3', [join(scripts, 'calculate-cost.py'), '--trial', f.root,
      '--model', 'k3', '--harness', 'pi-responses', '--score'], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const actual = JSON.parse(result.stdout);
    for (const [key, value] of Object.entries(expected)) assert.equal(actual[key], value, `${key}: ${JSON.stringify(raw)}`);
  }
});
