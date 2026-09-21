"""Read-only consistency checks for the contributed result, not a model rerun."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
load = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
d = load(HERE / 'results.json')
b = load(ROOT / 'results/eval-data.json')
profiles = load(HERE / 'config-profiles.json')
manifest = load(HERE / 'task-manifest.json')
assert sha(ROOT / 'results/eval-data.json') == d['published_baseline_sha256']
assert d['methodology_comparable'] is False and d['leaderboard_eligible'] is False
assert d['raw_evidence_public'] is False
ids = {x['id'] for x in manifest}
assert len(ids) == 30
assert Counter(x.split('/')[0] for x in ids) == {'terminal-bench': 21, 'datacurve': 9}
for task in manifest:
    folder = ROOT / 'tasks' / task['id'].split('/')[1]
    assert sha(folder / 'instruction.md') == task['instruction_sha256']
    assert sha(folder / 'task.toml') == task['task_toml_sha256']
assert len(d['trials']) == 120
assert len({(r['harness'], r['task_id']) for r in d['trials']}) == 120
csv_rows = []
for harness in d['harnesses']:
    name = harness['name']
    rows = [r for r in d['trials'] if r['harness'] == name]
    assert {r['task_id'] for r in rows} == ids
    assert len(rows) == harness['completed'] == harness['expected'] == 30
    assert sum(r['status'] == 'success' for r in rows) == harness['successful']
    old = next(x for x in b['harnesses'] if x['name'] == name)
    assert old['successful'] == harness['published_kimi_successful']
    previous = {x['id']: x['status'] for x in old['task_details']}
    pairs = Counter()
    for r in rows:
        assert r['version'] == harness['version']
        assert r['status'] in ('success', 'failure')
        assert r['reward'] == int(r['status'] == 'success')
        assert r['reward'] == r['verifier_rewards']['reward']
        assert r['phase_seconds']['agent_execution'] is not None
        assert r['config_profile'] in profiles and r['billed_cost_usd'] is None
        assert all(len(v) == 64 for v in r['local_evidence_sha256'].values())
        old_status = previous[r['task_id']]
        pair = ('both_pass' if r['status'] == 'success' else 'both_fail') if r['status'] == old_status else ('glm_only_pass' if r['status'] == 'success' else 'kimi_only_pass')
        pairs[pair] += 1
        csv_rows.append([r['task_id'], name, old_status, r['status']])
    assert dict(pairs) == harness['paired_outcomes']
    for suite, counts in harness['suites'].items():
        tasks = [r for r in rows if r['task_id'].startswith(suite + '/')]
        assert counts == {'expected': len(tasks), 'glm_passed': sum(r['status'] == 'success' for r in tasks), 'published_kimi_passed': sum(previous[r['task_id']] == 'success' for r in tasks)}
    print(f"{name}: {harness['successful']}/30; published Kimi {old['successful']}/30")
with (HERE / 'task-comparison.csv').open() as f:
    actual = list(csv.reader(f))
assert actual[0] == ['task_id', 'harness', 'published_kimi_status', 'glm_status']
assert sorted(actual[1:]) == sorted(csv_rows)
print('Validated 120 unique outcomes, four aggregates, suite/paired counts, CSV and 30 frozen task hashes.')
