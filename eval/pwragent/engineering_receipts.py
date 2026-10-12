"""Select per-request usage for explicitly named engineering turns only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from accounting import cost_components
from runtime import ROOT


def audit(session, turn_ids, output):
    selected=set(turn_ids);models={};requests={};totals={};terminal=set()
    source_digest=hashlib.sha256();source_bytes=0
    for line in Path(session).open('rb'):
        if not line.endswith(b'\n'):break
        event=json.loads(line);source_digest.update(line);source_bytes+=len(line)
        payload=event.get('payload') or {};turn=payload.get('turn_id')
        if turn not in selected:continue
        if event['type']=='turn_context':
            model=payload['model']
            if turn in models and models[turn]!=model:raise ValueError('Mixed model within selected turn')
            models[turn]=model
        elif event['type']=='token_usage_record':
            response=payload.get('response_id')
            if not response:raise ValueError('Missing response identity')
            key=(turn,response);safe={'turn_id':turn,'response_id':response,
                'timestamp':event['timestamp'],'usage':payload['usage']}
            if key in requests and requests[key]['usage']!=safe['usage']:
                raise ValueError('Conflicting duplicate usage record')
            requests[key]=safe;totals[turn]=payload['turn_token_usage']
        elif event['type']=='event_msg' and payload.get('type')=='task_complete':terminal.add(turn)
    card=json.loads((ROOT/'eval/pwragent/pricing-2026-10-11.json').read_text())
    keys=['input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens','total_tokens']
    turns=[]
    for turn in sorted(selected):
        rows=[r for (t,_),r in requests.items() if t==turn]
        if not rows or turn not in models:raise ValueError('No usage/model for selected turn')
        sums={key:sum(r['usage'].get(key,0) for r in rows) for key in keys}
        if sums!={key:totals[turn].get(key,0) for key in keys}:raise ValueError('Request totals do not reconcile')
        model=models[turn];price=0
        for row in rows:
            u=row['usage'];i=u['input_tokens'];c=u.get('cached_input_tokens',0)
            w=u.get('cache_write_input_tokens',0);o=u['output_tokens'];reason=u.get('reasoning_output_tokens',0)
            if i+o!=u['total_tokens'] or reason>o or c+w>i:raise ValueError('Invalid provider usage counters')
            rates=card['models'][model]['long' if i>272000 else 'short']
            components=cost_components(i,c,w,o,reason,rates)
            row['model']=model;row['cost_components_usd']=components
            row['estimated_cost_usd']=sum(components[k] for k in ['uncached_input_excluding_writes','cached_input','cache_writes','output_including_reasoning'])
            price+=row['estimated_cost_usd']
        turns.append(dict(turn_id=turn,model=model,complete=turn in terminal,request_count=len(rows),
                          tokens=sums,estimated_cost_usd=price,requests=rows))
    result=dict(schema_version=1,captured_at=datetime.now(timezone.utc).isoformat(),
                source_session_prefix_sha256=source_digest.hexdigest(),source_prefix_bytes=source_bytes,
                pricing_card_sha256=hashlib.sha256((ROOT/'eval/pwragent/pricing-2026-10-11.json').read_bytes()).hexdigest(),
                billing_basis='Standard-card API-equivalent estimate of selected provider requests, not an API invoice. Reasoning included in output. Active-turn tails and unknown helpers require separate reserves.',
                turns=turns,estimated_cost_usd=sum(t['estimated_cost_usd'] for t in turns))
    Path(output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'selected_turns':len(turns),'requests':sum(t['request_count'] for t in turns),
                      'all_complete':all(t['complete'] for t in turns),'estimated_cost_usd':result['estimated_cost_usd']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--turn',action='append',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();audit(args.session,args.turn,args.output)
