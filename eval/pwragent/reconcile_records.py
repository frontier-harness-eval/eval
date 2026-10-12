"""Offline reprice retained usage without rerunning models or changing grades."""
import hashlib
import json
import subprocess
from pathlib import Path
from accounting import account
from runtime import LOCAL


def reconcile():
    source=__import__('pathlib').Path(__file__).with_name('accounting.py')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    changed=0
    for path in sorted((LOCAL/'records').glob('*.json')):
        row=json.loads(path.read_text())
        if not row.get('dispatch_intent_at') or 'grade' not in row:
            continue
        output=LOCAL/'runs'/row['run_id']/'output'
        result=json.loads((output/'result.json').read_text())
        events=[json.loads(l) for l in (output/'rollout.jsonl').read_text().splitlines() if l.strip()]
        recovery=row.get('offline_pricing_recovery')
        if recovery:
            artifact=Path(recovery['artifact']).resolve()
            if not artifact.is_relative_to(output.resolve()) or hashlib.sha256(artifact.read_bytes()).hexdigest()!=recovery['artifact_sha256']:
                raise RuntimeError('Recovered pricing artifact provenance changed')
            recovered=json.loads(artifact.read_text())
            result={**result,'pricing':recovered['pricing']}
            events=recovered['selected_usage_notifications']
        updated=account(result,events)
        if abs(updated['conservative_budget_usd']-row['accounting']['conservative_budget_usd'])>0.000001:
            raise RuntimeError('Repricing changed conservative spend: ledger review required')
        if updated!=row['accounting']:
            row.setdefault('dispatch_accounting',row['accounting'])
            row['accounting']=updated
            row['offline_repricing']={'commit':commit,'accounting_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'reason':'request counter pricing coverage; grades and provider counters unchanged; no model calls'}
            path.write_text(json.dumps(row,indent=2)+'\n');changed+=1
    print(json.dumps({'offline_repriced_records':changed,'model_calls':0}))


if __name__=='__main__':reconcile()
