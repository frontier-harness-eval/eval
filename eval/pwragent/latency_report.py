"""Separate provider turn duration from setup/export/grading wall time."""
import argparse
import csv
import hashlib
import json
from runtime import LOCAL


def build(cohort):
    rows=[]
    for path in sorted((LOCAL/'records').glob('*.json')):
        r=json.loads(path.read_text())
        if r.get('cohort_id')!=cohort:continue
        protocol=LOCAL/'runs'/r['run_id']/'output/protocol.jsonl'
        terminal=None
        if protocol.exists() and r.get('turn_id'):
            for line in protocol.open():
                e=json.loads(line);envelope=e.get('envelope') or {}
                turn=(envelope.get('params') or {}).get('turn') or {}
                if envelope.get('method')=='turn/completed' and turn.get('id')==r['turn_id']:
                    terminal=dict(sequence=e['sequence'],timestamp_ms=e['timestamp'],
                                  status=turn.get('status'),duration_ms=turn.get('durationMs'))
        rows.append(dict(run_id=r['run_id'],model=r['cell']['model'],token_miser=r['cell']['token_miser'],
            agent_status=r.get('agent_status'),provider_terminal_status=(terminal or {}).get('status'),
            provider_parent_duration_seconds=((terminal['duration_ms']/1000)
                if terminal and terminal['duration_ms'] is not None else None),
            setup_execution_export_and_grading_seconds=r.get('duration_seconds'),
            terminal_sequence=(terminal or {}).get('sequence'),
            protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest() if protocol.exists() else None,
            zero_dispatch=bool(r.get('zero_dispatch_reconciliation'))))
    dest=LOCAL/('report-'+cohort);dest.mkdir(exist_ok=True)
    (dest/'latency.json').write_text(json.dumps(dict(cohort_id=cohort,rows=rows,
        interpretation='Provider parent duration includes the agent turn and tools. Full evaluator duration additionally includes container preparation, export and hidden grading. Missing terminal timing stays unknown; helper durations overlap and are not added.'),indent=2)+'\n')
    if rows:
        with (dest/'latency.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return dest/'latency.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cohort',required=True)
    print(build(parser.parse_args().cohort))
