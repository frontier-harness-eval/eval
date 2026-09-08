import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

for (const [name, rates, aggregate, expected, coverage] of [
  ['complete', [0.6, 0.9], 0.75, '75.0%', '2/2'],
  ['partial', [0.6, null], null, '60.0% (partial)', '1/2'],
  ['measured zero', [0, null], null, '0.0% (partial)', '1/2'],
  ['unavailable', [null, null], null, 'Unavailable', '0/2'],
]) {
  test(`report shows ${name} cache measurements without changing aggregates`, t => {
    const root = mkdtempSync(join(tmpdir(), 'fh-cache-report-'));
    t.after(() => rmSync(root, { recursive: true, force: true }));
    mkdirSync(join(root, 'report'));
    const candidate = {
      label: 'Test Harness', comparable: false, successful: 2, completed: 2, expected: 3,
      pass_rate: 1, cache_hit_rate_typical: aggregate,
      task_details: rates.map((rate, i) => ({ id: `task-${i}`, status: 'success', success: true, cache_hit_rate_normalized: rate })),
    };
    // A failure with a measured rate must not enter the success-only median.
    candidate.task_details.push({ id: 'failed', status: 'failure', success: false, cache_hit_rate_normalized: 1 });
    writeFileSync(join(root, 'candidate.json'), JSON.stringify(candidate));
    writeFileSync(join(root, 'run.json'), '{}');
    writeFileSync(join(root, 'baseline.json'), '{"harnesses":[]}');
    writeFileSync(join(root, 'report/chart.svg'), '<svg xmlns="http://www.w3.org/2000/svg"/>');
    const result = spawnSync(process.execPath, [resolve('skills/frontierharness-eval/scripts/build-report.mjs'), '--run', root, '--baseline', join(root, 'baseline.json')], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    for (const file of ['REPORT.md', 'index.html']) {
      const report = readFileSync(join(root, 'report', file), 'utf8');
      assert.ok(report.includes(expected), file);
      assert.ok(report.includes(coverage), file);
      assert.ok(report.includes('Cache hit rate'), file);
      if (rates.includes(null)) assert.ok(report.includes('Missing complete cache usage: task-'), file);
    }
    assert.deepEqual(JSON.parse(readFileSync(join(root, 'candidate.json'))), candidate);
  });
}

test('exclusive solve highlights require a valid failure from every baseline', t => {
  const root = mkdtempSync(join(tmpdir(), 'fh-exclusive-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, 'report'));
  writeFileSync(join(root, 'run.json'), '{}');
  writeFileSync(join(root, 'report/chart.svg'), '<svg/>');
  writeFileSync(join(root, 'candidate.json'), JSON.stringify({label:'Candidate', successful:1, completed:1, expected:2, pass_rate:1, comparable:false,
    task_details:[{id:'a',status:'success',success:true,duration_seconds:132}]}));
  const failure = {id:'a',status:'failure',success:false};
  for (const [cells, qualifies] of [[[failure],true], [[],false], [[{...failure,status:'infra_invalid'}],false], [[{...failure,status:'success',success:true}],false], [[failure,failure],false]]) {
    writeFileSync(join(root, 'baseline.json'), JSON.stringify({harnesses:[{name:'one',task_details:[failure]}, {name:'two',task_details:cells}]}));
    const result=spawnSync(process.execPath,[resolve('skills/frontierharness-eval/scripts/build-report.mjs'),'--run',root,'--baseline',join(root,'baseline.json')],{encoding:'utf8'});
    assert.equal(result.status,0,result.stderr);
    const html=readFileSync(join(root,'report/index.html'),'utf8');
    const md=readFileSync(join(root,'report/REPORT.md'),'utf8');
    assert.equal(html.includes('<tr class="exclusive-solve">'),qualifies);
    assert.equal(md.includes('★ Solved · 0/2 baselines passed'),qualifies);
    if(qualifies){assert.ok(md.includes('**2m 12s**'));assert.ok(html.includes('conditions are not established as equivalent'));}
  }
});
