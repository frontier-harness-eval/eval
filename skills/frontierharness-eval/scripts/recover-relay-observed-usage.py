"""Derive diagnostic cache coverage from retained relay records; never fill canonical metrics."""
import json
import sys
from pathlib import Path
run = Path(sys.argv[1])
audit_path = run / 'observed-cost-audit.json'
audit = json.loads(audit_path.read_text())
candidate = json.loads((run / 'candidate.json').read_text())
for task in candidate['task_details']:
    measured = next((x for x in audit['tasks'] if x['task'] == task['id']), None)
    if measured is None:
        continue
    inputs = cached = 0
    for path in (run / task['evidence']).rglob('kimi-relay.jsonl'):
        rows = {}
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record.get('usage') and record.get('request_id'):
                rows[record['request_id']] = record['usage']
        for usage in rows.values():
            value = usage.get('input_tokens')
            read = (usage.get('input_tokens_details') or {}).get('cached_tokens')
            if isinstance(value, int) and isinstance(read, int) and 0 <= read <= value:
                inputs += value
                cached += read
    measured['observed_raw_cache_rate'] = cached / inputs if inputs else None
    measured['cache_basis'] = 'Raw cached/input ratio across recorded usage only; no first-call adjustment; excludes missing calls.'
audit_path.write_text(json.dumps(audit, indent=2) + '\n')
