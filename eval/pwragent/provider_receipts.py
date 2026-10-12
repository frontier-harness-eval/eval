"""Export only token/terminal/rate-limit fields from local provider sessions."""
import hashlib
import json
from pathlib import Path
from runtime import LOCAL


def export(cohort=None):
    count=0
    for record in sorted((LOCAL/'records').glob('*.json')):
        row=json.loads(record.read_text());thread=row.get('thread_id')
        if cohort and row.get('cohort_id')!=cohort:continue
        if not thread or not row.get('dispatch_intent_at'):continue
        root=LOCAL/'runs'/row['run_id'];receipts=[]
        for session in (root/'codex/sessions').rglob('*.jsonl'):
            entries=[json.loads(l) for l in session.read_text().splitlines() if l.strip()]
            meta=next((e.get('payload',{}) for e in entries if e.get('type')=='session_meta'),{})
            if meta.get('id')!=thread:continue
            safe=[]
            for e in entries:
                p=e.get('payload',{});kind=p.get('type')
                if e.get('type')!='event_msg':continue
                if kind=='token_count':
                    rate=p.get('rate_limits') or {};limits={}
                    for period in ['primary','secondary']:
                        if isinstance(rate.get(period),dict):limits[period]={k:rate[period].get(k) for k in ['used_percent','window_minutes','resets_at'] if k in rate[period]}
                    if rate.get('plan_type'):limits['plan_type']=rate['plan_type']
                    if isinstance(rate.get('credits'),dict):limits['credits']={k:rate['credits'][k] for k in ['has_credits','unlimited','balance'] if k in rate['credits']}
                    safe.append({'timestamp':e.get('timestamp'),'type':kind,'info':p.get('info'),'rate_limits':limits})
                elif kind in ['turn_aborted','task_complete','task_started']:
                    safe.append({'timestamp':e.get('timestamp'),'type':kind,**{k:p[k] for k in ['root_turn_id','turn_id','reason','started_at','completed_at','duration_ms'] if k in p}})
            receipts.append({'source_session_sha256':hashlib.sha256(session.read_bytes()).hexdigest(),'session_id':thread,'events':safe})
        (root/'output/provider-receipt.json').write_text(json.dumps({'schema_version':1,'run_id':row['run_id'],'billing_limitation':'Provider-reported usage and subscription limits; no billing invoice. Cancelled in-flight usage may be incomplete; ledger retains full reservation.','sessions':receipts},indent=2)+'\n');count+=1
    print(json.dumps({'receipt_exports':count,'model_calls':0}))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--cohort');export(p.parse_args().cohort)
