import test from 'node:test';
import { installTaskSources } from './fixtures/task-inputs.mjs';
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const repo = fileURLToPath(new URL('../', import.meta.url));
const scripts = join(repo, 'skills/frontierharness-eval/scripts');
const quote = value => `'${value.replaceAll("'", "'\\''")}'`;

// Same transport doubles as pipeline.test.mjs: fake harbor/pier write result
// evidence, fake docker absorbs pulls, fake timeout adds the watchdog exit code.
// Nothing contacts Docker, a model provider, or the network.
function fixture(t, config = {}) {
  const root = mkdtempSync(join(tmpdir(), 'fh-local-'));
  t.after(() => process.env.KEEP_FH_FIXTURES ? t.diagnostic(root) : rmSync(root, { recursive: true, force: true }));
  const bin = join(root, 'bin');
  mkdirSync(bin);
  installTaskSources(root, repo, bin);
  const env = { ...process.env, PATH: `${bin}:${process.env.PATH}`, FAKE_RUNTA_ROOT: root, FH_TASK_PLATFORM: 'linux/amd64', FIREWORKS_API_KEY: 'test-key' };
  const executable = (name, content) => writeFileSync(join(bin, name), content, { mode: 0o755 });
  const node = process.execPath;
  for (const name of ['harbor', 'pier']) executable(name, `#!/bin/sh\nexec ${quote(node)} ${quote(join(repo, 'tests/fixtures/runner.cjs'))} ${name} "$@"\n`);
  executable('runta', '#!/bin/sh\ntouch "$FAKE_RUNTA_ROOT/unexpected-runta"\nexit 99\n');
  executable('docker', `#!/bin/sh
if [ "$1 $2" = "image inspect" ]; then
  [ "$FAKE_INSPECT_FAIL" != 1 ] || exit 1
  printf '[{"Os":"linux","Architecture":"%s","RepoDigests":["fixture@sha256:abc"]}]\\n' "\${FAKE_IMAGE_ARCH:-amd64}"
elif [ "$1" = pull ]; then
  echo "pulled $*"
else
  echo 'Docker fixture'
fi
`);
  executable('timeout', '#!/usr/bin/env python3\nimport json, os, sys\na = sys.argv[1:]\nif a == ["--version"]: print("GNU timeout"); sys.exit(0)\nif a[0].startswith("--kill-after"): a.pop(0)\na.pop(0)\nc = json.load(open(os.path.join(os.environ["FAKE_RUNTA_ROOT"], "config.json")))\nif c.get("runnerTimeout") and a[0] == "bash": sys.exit(124)\nos.execvp(a[0], a)\n');
  writeFileSync(join(root, 'config.json'), JSON.stringify(config));
  // A fake DeepSWE corpus at the layout the runner resolves images from.
  const deepSwe = join(root, 'deep-swe');
  mkdirSync(join(deepSwe, 'tasks/httpx-multipart-response-parsing'), { recursive: true });
  writeFileSync(join(deepSwe, 'tasks/httpx-multipart-response-parsing/task.toml'), 'docker_image = "public.ecr.aws/test/httpx:v1.1"\n');
  // The benchmark workspace files the scoring and report chain reads from cwd.
  for (const entry of ['benchmark.json', 'results', 'tasks/regex-log']) {
    cpSync(join(repo, entry), join(root, entry), { recursive: true });
  }
  const tasks = join(root, 'tasks.txt');
  writeFileSync(tasks, 'terminal-bench/regex-log\ndatacurve/httpx-multipart-response-parsing\n');
  const run = (extra = [], envOverride) => spawnSync('bash', [join(scripts, 'run-trials-local.sh'),
    '--harness', 'pi-responses', '--run-id', 'local', '--tasks', tasks, '--deep-swe', deepSwe,
    '--out', join(root, 'runs'), '--timeout', '5', ...extra],
    { cwd: root, env: envOverride ?? env, encoding: 'utf8', timeout: 30000 });
  const json = file => JSON.parse(readFileSync(file, 'utf8'));
  const cli = (...args) => spawnSync(process.execPath, [join(repo, 'cli/index.mjs'), ...args, '--dir', root],
    { cwd: root, env, encoding: 'utf8', timeout: 30000 });
  return { root, env, run, json, cli, tasks,
    trialDir: slug => join(root, 'runs/local/trials', slug),
    trial: slug => json(join(root, 'runs/local/trials', slug, 'trial.json')),
    executions: () => existsSync(join(root, 'executions.jsonl'))
      ? readFileSync(join(root, 'executions.jsonl'), 'utf8').trim().split('\n').length : 0,
    setConfig: value => writeFileSync(join(root, 'config.json'), JSON.stringify(value)) };
}
const ok = result => assert.equal(result.status, 0, `${result.error || ''}\n${result.stderr}\n${result.stdout}`);

test('local runner scores both suites and feeds the normalize/chart/report chain', t => {
  const f = fixture(t);
  ok(f.run());
  for (const slug of ['terminal-bench-regex-log', 'datacurve-httpx-multipart-response-parsing']) {
    assert.equal(f.trial(slug).status, 'success');
    assert.equal(f.trial(slug).cost_usd, 0.000045);
    assert.equal(f.trial(slug).cost_first_cold_usd, null, 'reported billing alone cannot establish first-cold cost');
  }
  assert.equal(f.run([], { ...f.env, FH_TASK_PLATFORM: 'linux/arm64' }).status, 2);
  assert.ok(readFileSync(join(f.trialDir('terminal-bench-regex-log'), 'pull.log'), 'utf8').includes('alexgshaw/regex-log:20251031'));
  assert.ok(readFileSync(join(f.trialDir('datacurve-httpx-multipart-response-parsing'), 'pull.log'), 'utf8').includes('public.ecr.aws/test/httpx:v1.1'));
  const run = f.json(join(f.root, 'runs/local/run.json'));
  assert.equal(run.topology, 'local-docker');
  assert.equal(run.egress_policy.mode, 'unrestricted');
  assert.equal(run.methodology_comparable, false);
  assert.equal(f.executions(), 2);
  ok(f.run());
  assert.equal(f.executions(), 2, 'first valid attempts remain canonical');

  for (const script of ['normalize-results.mjs', 'generate-chart.mjs', 'build-report.mjs']) {
    ok(spawnSync(process.execPath, [join(scripts, script), '--run', 'runs/local'],
      { cwd: f.root, env: f.env, encoding: 'utf8', timeout: 20000 }));
  }
  const candidate = f.json(join(f.root, 'runs/local/candidate.json'));
  assert.equal(candidate.successful, 2);
  assert.equal(candidate.expected, 30);
  assert.equal(candidate.comparable, false);
  const report = readFileSync(join(f.root, 'runs/local/report/REPORT.md'), 'utf8');
  assert.match(report, /Local Docker/);
  assert.doesNotMatch(report, /ranking (?:\*\*)?\d+ of/);
});

test('installed CLI defaults to Docker, freezes both inputs, resumes and rejects backend changes', t => {
  const f = fixture(t);
  ok(f.cli('install', '--agent', 'none'));
  ok(f.cli('doctor', '--tasks', f.tasks));
  ok(f.cli('run', '--run-id', 'local', '--harness', 'pi', '--tasks', f.tasks, '--no-prepull'));
  const run = f.json(join(f.root, 'runs/local/run.json'));
  assert.equal(run.backend, 'local-docker');
  assert.equal(run.task_source, 'repository-v1');
  const input = join(f.trialDir('terminal-bench-regex-log'), 'inputs/regex-log');
  assert.equal(readFileSync(join(input, 'instruction.md'), 'utf8'), readFileSync(join(repo, 'tasks/regex-log/instruction.md'), 'utf8'));
  assert.ok(!existsSync(join(input, 'solution')));
  assert.equal(f.json(join(input, 'input-manifest.json')).commit, '69671fbaac6d67a7ef0dfec016cc38a64ef7a77c');
  const calls = readFileSync(join(f.root, 'executions.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  for (const args of calls) {
    assert.ok(args.includes('FIREWORKS_AI_API_KEY=\${FIREWORKS_API_KEY}'));
    assert.ok(!JSON.stringify(args).includes('test-key'));
    assert.ok(args.includes('-p'));
  }
  ok(f.cli('run', '--tasks', f.tasks, '--run-id', 'local'));
  assert.equal(f.executions(), 2);
  assert.equal(f.cli('run', '--run-id', 'local', '--checkpoint', 'other').status, 2);
  assert.equal(existsSync(join(f.root, 'unexpected-runta')), false);
  for (const cmd of ['normalize', 'chart', 'report']) ok(f.cli(cmd, '--run', 'runs/local'));
  assert.ok(existsSync(join(f.root, 'runs/local/report/index.html')));
});

test('passes a custom harness and model route through both suite runners', t => {
  const f = fixture(t);
  ok(f.run(['--harness', 'custom-agent', '--provider', 'custom', '--model', 'example/selected-model',
    '--secret-name', 'TEST_MODEL_KEY', '--secret-host', 'models.example.org'], { ...f.env, TEST_MODEL_KEY: 'fixture-value' }));
  const calls = readFileSync(join(f.root, 'executions.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(calls.length, 2);
  for (const args of calls) {
    assert.ok(args.includes('custom-agent'));
    assert.ok(args.includes('example/selected-model'));
    assert.ok(args.includes('TEST_MODEL_KEY=${TEST_MODEL_KEY}'));
    assert.ok(!JSON.stringify(args).includes('fixture-value'));
  }
  assert.ok(calls.find(args => args[0] === 'harbor').includes('models.example.org'));
  assert.equal(existsSync(join(f.root, 'unexpected-runta')), false);
});

test('a runner crash is infra_invalid and may be retried', t => {
  const f = fixture(t, { runnerCrash: true });
  assert.equal(f.run().status, 1);
  assert.equal(f.trial('terminal-bench-regex-log').status, 'infra_invalid');
  assert.equal(f.trial('terminal-bench-regex-log').success, false);
  assert.equal(f.executions(), 2);
  f.setConfig({});
  ok(f.run());
  assert.equal(f.trial('terminal-bench-regex-log').status, 'success');
  assert.equal(f.executions(), 4, 'invalid attempts may be retried');
});

test('a verifier failure with usage is a valid failure and stays canonical', t => {
  const f = fixture(t, { result: { resolved: false, reward: 1, agent_result: { n_input_tokens: 10 } } });
  ok(f.run());
  assert.equal(f.trial('terminal-bench-regex-log').status, 'failure');
  assert.equal(f.trial('terminal-bench-regex-log').success, false);
  assert.equal(f.executions(), 2);
  ok(f.run());
  assert.equal(f.executions(), 2, 'valid failures are never retried');
  assert.equal(f.trial('terminal-bench-regex-log').status, 'failure');
});

test('the run refuses to start without the provider key in the environment', t => {
  const f = fixture(t);
  const without = { ...f.env };
  delete without.FIREWORKS_API_KEY;
  delete without.FIREWORKS_AI_API_KEY;
  const result = f.run([], without);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /FIREWORKS_API_KEY/);
  assert.equal(f.executions(), 0, 'no trial may launch without credentials');
});

test('bundled DSH resolves from an installed workspace and resumes its Responses route', t => {
  const f = fixture(t);
  writeFileSync(f.tasks, 'terminal-bench/regex-log\n');
  f.env.ARK_TEST_KEY = 'test-credential-value';
  ok(f.cli('install', '--agent', 'none'));
  const args = ['--tasks', f.tasks, '--run-id', 'local'];
  const route = ['--harness', 'dsh', '--provider', 'custom', '--model', 'fixture',
    '--base-url', 'https://inference.test/v3', '--secret-name', 'ARK_TEST_KEY'];
  ok(f.cli('run', ...route, ...args, '--dsh-web-search-max-keywords', '2'));
  const [call] = readFileSync(join(f.root, 'executions.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(call[call.indexOf('-a') + 1], 'adapters.dsh.agent:DeepSeekHarness');
  for (const value of ['inference.test', 'web_search_max_keywords=2', 'secret_name=ARK_TEST_KEY']) {
    assert.ok(call.includes(value));
  }
  assert.ok(!call.includes('--agent-env'));
  assert.ok(!JSON.stringify(call).includes(f.env.ARK_TEST_KEY));
  ok(f.cli('run', ...args));
  assert.equal(f.executions(), 1);
  assert.equal(f.cli('run', ...args, '--dsh-web-search-max-keywords', '3').status, 2);
  assert.equal(f.cli('run', ...args, '--base-url', 'https://inference.test/v4').status, 2);
});

test('hosted search is opt-in and the DSH shortcut checks suite and credential scope', t => {
  const f = fixture(t);
  const route = ['--harness', 'dsh', '--provider', 'custom', '--model', 'fixture'];
  const env = { ...f.env, OPENAI_API_KEY: 'test-only', OPENAI_BASE_URL: 'https://inference.test/v3' };
  writeFileSync(f.tasks, 'terminal-bench/regex-log\n');
  assert.equal(f.run([...route, '--dsh-web-search-max-keywords', '-1'], env).status, 2);
  assert.equal(f.run([...route, '--secret-host', 'other.test'], env).status, 2);
  assert.equal(f.run([...route, '--harness', 'codex', '--dsh-web-search-max-keywords', '2'], env).status, 2);
  assert.equal(f.executions(), 0);
  ok(f.run(route, env));
  ok(f.run([...route, '--harness', 'codex', '--run-id', 'codex-test'], env));
  const [dsh, codex] = readFileSync(join(f.root, 'executions.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  assert.ok(!dsh.some(value => value.includes('web_search')));
  assert.ok(dsh.includes('secret_name=OPENAI_API_KEY'));
  assert.equal(codex[codex.indexOf('-a') + 1], 'codex');
});

test('the three DSH presets use their requested identity for Harbor and Pier on Fireworks', t => {
  const f = fixture(t);
  for (const harness of ['dsh-standard', 'dsh-ptc', 'dsh-creator']) {
    ok(f.run(['--harness', harness, '--provider', 'fireworks', '--run-id', harness]));
    const calls = readFileSync(join(f.root, 'executions.jsonl'), 'utf8').trim().split('\n').slice(-2).map(JSON.parse);
    const harbor = calls.find(args => args[0] === 'harbor');
    const pier = calls.find(args => args[0] === 'pier');
    assert.equal(harbor[harbor.indexOf('-a') + 1], 'adapters.dsh.agent:DeepSeekHarness');
    assert.equal(pier[pier.indexOf('--agent-import-path') + 1], 'adapters.dsh.pier_agent:DeepSeekHarness');
    for (const args of calls) {
      assert.ok(args.includes(`harness=${harness}`));
      assert.ok(args.includes('api=openai-completions'));
      assert.ok(args.includes('base_url=https://api.fireworks.ai/inference/v1'));
      assert.ok(!args.includes('--agent-env'));
    }
    const run = f.json(join(f.root, 'runs', harness, 'run.json'));
    assert.equal(run.harness, harness);
    assert.equal(run.model, 'fireworks_ai/accounts/fireworks/models/kimi-k3');
  }
  assert.equal(f.run(['--harness', 'dsh-ptc', '--dsh-web-search-max-keywords', '2']).status, 2);
});

test('custom adapters reach both runners by import path and are pinned to the run', t => {
  const f = fixture(t);
  ok(f.run(['--harbor-agent-import-path', 'my_adapter.harbor:MyAgent',
    '--pier-agent-import-path', 'my_adapter.pier:MyAgent']));
  const calls = readFileSync(join(f.root, 'executions.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  const harbor = calls.find(args => args[0] === 'harbor');
  const pier = calls.find(args => args[0] === 'pier');
  assert.equal(harbor[harbor.indexOf('-a') + 1], 'my_adapter.harbor:MyAgent');
  assert.equal(pier[pier.indexOf('--agent-import-path') + 1], 'my_adapter.pier:MyAgent');
  assert.ok(!pier.includes('--agent'), 'Pier rejects unknown --agent names, so the name must not be passed');
  const run = f.json(join(f.root, 'runs/local/run.json'));
  assert.equal(run.harbor_agent_import_path, 'my_adapter.harbor:MyAgent');
  assert.equal(run.pier_agent_import_path, 'my_adapter.pier:MyAgent');
  assert.ok(run.methodology_notes.some(note => note.includes('my_adapter.pier:MyAgent')));
  assert.equal(f.run(['--harbor-agent-import-path', 'my_adapter.harbor:MyAgent']).status, 2,
    'a resume may not drop or change an adapter');
  assert.equal(f.executions(), 2);
});

test('malformed import paths and import paths with --cmd are refused before any trial', t => {
  const f = fixture(t);
  for (const path of ['not-a-path', 'my..adapter:Agent', 'my.:Agent', 'my.1adapter:Agent']) {
    assert.equal(f.run(['--pier-agent-import-path', path]).status, 2, path);
  }
  assert.equal(f.run(['--pier-agent-import-path', 'a.b:C', '--cmd', 'true']).status, 2);
  assert.equal(f.executions(), 0);
});

test('Harbor keeps the first attempt and records input and image provenance', t => {
  const f = fixture(t);
  ok(f.run());
  const harbor = readFileSync(join(f.root, 'executions.jsonl'), 'utf8').trim().split('\n').map(JSON.parse)
    .find(args => args[0] === 'harbor');
  assert.equal(harbor[harbor.indexOf('-r') + 1], '0');
  const runFile = join(f.root, 'runs/local/run.json');
  const run = f.json(runFile);
  assert.equal(run.harbor_retries, 0);
  for (const pattern of [/terminal-bench-2 at 69671fb/, /patch collector/, /pyknotid/]) {
    assert.ok(run.methodology_notes.some(note => pattern.test(note)), `missing note ${pattern}`);
  }
  const image = f.json(join(f.trialDir('terminal-bench-regex-log'), 'image.json'));
  assert.equal(image.resolved_platform, 'linux/amd64');
  assert.equal(image.platform_matches, true);
  assert.deepEqual(image.repo_digests, ['fixture@sha256:abc']);
  // A recorded internal retry could have replaced the first valid attempt.
  run.harbor_retries = 2;
  writeFileSync(runFile, JSON.stringify(run));
  assert.equal(f.run().status, 2);
});

test('a pulled image on the wrong architecture stops before the agent runs', t => {
  const f = fixture(t);
  const result = f.run([], { ...f.env, FAKE_IMAGE_ARCH: 'arm64' });
  assert.equal(result.status, 1);
  assert.equal(f.executions(), 0, 'no model spend on a mismatched image');
  const trial = f.trial('terminal-bench-regex-log');
  assert.equal(trial.status, 'infra_invalid');
  assert.match(trial.error, /linux\/arm64/);
  assert.equal(f.json(join(f.trialDir('terminal-bench-regex-log'), 'image.json')).platform_matches, false);
  ok(f.run());
  assert.equal(f.trial('terminal-bench-regex-log').status, 'success', 'the infra-invalid attempt is retried');
});

test('legacy manifests resume across Harbor and Pier task subsets', t => {
  const f = fixture(t);
  ok(f.run());
  const file = join(f.root, 'runs/local/run.json');
  const run = f.json(file);
  for (const field of ['harbor_retries', 'harbor_agent_import_path', 'pier_agent_import_path']) delete run[field];
  writeFileSync(file, JSON.stringify(run));
  ok(f.run());
  writeFileSync(f.tasks, 'datacurve/httpx-multipart-response-parsing\n');
  ok(f.run());
  run.harbor_retries = 2;
  writeFileSync(file, JSON.stringify(run));
  ok(f.run());
  assert.equal(f.executions(), 2);
});

test('unavailable image metadata preserves scores without pre-pull and gates a pre-pull', t => {
  const f = fixture(t);
  const env = { ...f.env, FAKE_INSPECT_FAIL: '1' };
  const slugs = ['terminal-bench-regex-log', 'datacurve-httpx-multipart-response-parsing'];
  assert.equal(f.run([], env).status, 1);
  for (const slug of slugs) assert.equal(f.trial(slug).status, 'infra_invalid');
  assert.equal(f.executions(), 0);

  ok(f.run(['--no-prepull'], env));
  for (const slug of slugs) {
    const image = f.json(join(f.trialDir(slug), 'image.json'));
    assert.equal(image.prepulled, false);
    assert.equal(image.resolved_platform, null);
    assert.equal(image.platform_matches, null);
    assert.equal(image.repo_digests, null);
    assert.equal(f.trial(slug).status, 'success');
  }
  assert.equal(f.executions(), 2);
});

test('the CLI resumes a run with its recorded adapters', t => {
  const f = fixture(t);
  ok(f.cli('install', '--agent', 'none'));
  ok(f.cli('run', '--run-id', 'local', '--harness', 'my-harness', '--tasks', f.tasks,
    '--pier-agent-import-path', 'my_adapter.pier:MyAgent'));
  ok(f.cli('run', '--run-id', 'local', '--tasks', f.tasks));
  assert.equal(f.executions(), 2, 'resume reuses the recorded adapter and keeps valid attempts');
});
