"""Reconcile all native parent requests, including Codex context compaction."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from accounting import account, CARD, cost_components
from ledger import Ledger
from runtime import LOCAL

KEYS=['input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens','total_tokens']
WIRE=['inputTokens','cachedInputTokens','cacheWriteInputTokens','outputTokens','reasoningOutputTokens','totalTokens']


def extra_requests(native, wire):
    remaining=Counter(tuple(r.get(k,0) for k in WIRE) for r in wire)
    extra=[]
    for row in native:
        key=tuple(row['usage'][k] for k in KEYS)
        if remaining[key]:remaining[key]-=1
        else:extra.append(row)
    if any(remaining.values()):raise ValueError('App request has no matching native receipt')
    if any(not r['followed_by_compaction'] for r in extra):
        raise ValueError('Unclassified native request; retain uncertainty')
    return extra


def inspect(record):
    if record.get('runtime',{}).get('version')!='0.162.1-pwragent.1':
        raise ValueError('Verify the native compaction model path for this runtime before repricing')
    root=LOCAL/'runs'/record['run_id'];result=json.loads((root/'output/result.json').read_text())
    events=[json.loads(l) for l in (root/'output/rollout.jsonl').read_text().splitlines() if l.strip()]
    base=account(result,events);parent=next(r for r in base['rows'] if r['usage_role']=='parent')
    matches=[]
    for path in (root/'codex/sessions').rglob('*.jsonl'):
        with path.open() as f:
            first=json.loads(f.readline())
            if first.get('payload',{}).get('id')==result['threadId']:matches.append(path)
    if len(matches)!=1:raise ValueError('Exactly one native parent session required')
    path=matches[0];data=path.read_bytes();native_events=[json.loads(l) for l in data.splitlines() if l.strip()]
    native={};last_total=None;models=set();terminal=False
    for index,event in enumerate(native_events):
        p=event.get('payload') or {}
        if event.get('type')=='turn_context' and p.get('turn_id')==result['turnId']:models.add(p['model'])
        if event.get('type')=='event_msg' and p.get('type')=='task_complete' and p.get('turn_id')==result['turnId']:terminal=True
        if event.get('type')!='token_usage_record' or p.get('turn_id')!=result['turnId']:continue
        usage=p['usage'];assert all(k in usage for k in KEYS)
        assert usage['input_tokens']+usage['output_tokens']==usage['total_tokens']
        assert usage['reasoning_output_tokens']<=usage['output_tokens']
        rid=p['response_id'];assert rid not in native,'Duplicate native response identity'
        native[rid]=dict(response_id=rid,timestamp=event['timestamp'],usage=usage,
                        followed_by_compaction=index+1<len(native_events) and native_events[index+1]['type']=='compacted')
        last_total=p['turn_token_usage']
    assert models=={record['cell']['model']} and native
    totals={k:sum(r['usage'][k] for r in native.values()) for k in KEYS}
    assert totals=={k:last_total[k] for k in KEYS},'Native request totals must reconcile exactly'
    extras=extra_requests(list(native.values()),parent['provider_requests'])
    proof=dict(run_id=record['run_id'],thread_id=result['threadId'],turn_id=result['turnId'],model=record['cell']['model'],
        native_session_sha256=hashlib.sha256(data).hexdigest(),native_request_count=len(native),
        app_request_count=len(parent['provider_requests']),native_totals=totals,
        native_terminal_event_observed=terminal,parent_outcome=record['agent_status'],
        requests=list(native.values()),compaction_requests=extras,
        source_model_proof='https://github.com/pwrdrvr/codex/blob/c03dc0f3a79ee087d4de66150a39c89c4a508f9d/codex-rs/core/src/compact.rs#L779',
        interpretation='Compaction streams use turn_context.model_info(), record the completed request, then compact history. These observed completed requests are additional to the App Server pricing rows. Failed overall turns and unresolved helpers retain their uncertainty envelopes.')
    (root/'output/native-request-reconciliation.json').write_text(json.dumps(proof,indent=2)+'\n')
    return base,proof


def add_native_usage(record,base,proof):
    extra_rows=[]
    for request in proof['compaction_requests']:
        u=request['usage'];model=record['cell']['model'];rate=CARD['models'][model]['long' if u['input_tokens']>272000 else 'short']
        parts=cost_components(u['input_tokens'],u['cached_input_tokens'],u['cache_write_input_tokens'],u['output_tokens'],u['reasoning_output_tokens'],rate)
        long=CARD['models'][model]['long'];short=CARD['models'][model]['short'];uncached=u['input_tokens']-u['cached_input_tokens']
        cost=lambda rates:((uncached-u['cache_write_input_tokens'])*rates[0]+u['cached_input_tokens']*rates[1]+u['cache_write_input_tokens']*rates[2]+u['output_tokens']*rates[3])/1e6
        extra_rows.append(dict(usage_line_id='native:'+request['response_id'],model=model,scope='native_compaction',status='finalized',
            protocol_reconciled=False,native_request_reconciled=True,service_tier='default',
            input_tokens=u['input_tokens'],uncached_input_tokens=uncached,cached_input_tokens=u['cached_input_tokens'],cache_write_tokens=u['cache_write_input_tokens'],
            output_tokens=u['output_tokens'],reasoning_tokens=u['reasoning_output_tokens'],nonreasoning_output_tokens=u['output_tokens']-u['reasoning_output_tokens'],
            peak_context_tokens=u['input_tokens'],provider_equivalent_cost_usd=None,app_catalog_missing_request=True,
            estimated_cost_usd=cost(rate),projected_short_usd=cost(short),projected_long_usd=cost(long),
            conservative_budget_usd=(uncached*max(long[0],long[2])+u['cached_input_tokens']*long[1]+u['output_tokens']*long[3])/1e6,
            turn_usage_attributed=True,provider_requests=[],usage_role='codex_compaction',source_item_id='native:compaction:'+request['response_id'],
            estimated_cost_components_usd=parts,provider_request_coverage_complete=True,reported_usage_only=False))
    original=record['accounting'];base['rows']+=extra_rows
    base['usage_complete']=original['usage_complete'] and proof['native_terminal_event_observed'] and record['agent_status']=='completed'
    base['unpriced_models']=list(dict.fromkeys(base['unpriced_models']+original['unpriced_models']))
    for key in ['missing_usage','completeness_correction','pricing_rows_complete']:
        if key in original:base[key]=original[key]
    for total,field in [('estimated_cost_usd','estimated_cost_usd'),('projected_cost_lower_usd','projected_short_usd'),('projected_cost_upper_usd','projected_long_usd'),('conservative_budget_usd','conservative_budget_usd')]:
        base[total]=sum(r[field] for r in base['rows'])
    evidence=LOCAL/'runs'/record['run_id']/'output/native-request-reconciliation.json'
    record['accounting']=base;record['native_request_reconciliation']=dict(receipt_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),native_request_count=proof['native_request_count'],compaction_request_count=len(extra_rows),compaction_cost_usd=sum(r['estimated_cost_usd'] for r in extra_rows))
    if record.get('late_provider_usage_backfill'):
        record['late_provider_usage_backfill']['superseded_by']='Native request reconciliation identifies the extra usage as Codex compaction and separates it from normal parent requests; no double counting.'
    return sum(r['conservative_budget_usd'] for r in extra_rows)


def apply(record,path,base,proof,ledger):
    if record.get('native_request_reconciliation'):return
    backup=LOCAL/'record-revisions'/(record['run_id']+'.before-native-compaction.json');assert not backup.exists()
    backup.write_bytes(path.read_bytes())
    supplement=add_native_usage(record,base,proof)
    entry=next(e for e in ledger.snapshot()['entries'] if e['run_id']==record['run_id'])
    if supplement and entry['status']=='settled':
        rid=record['run_id']+'-native-compaction-accounting'
        ledger.reserve(rid,supplement,'Offline correction: observed native compaction omitted by app pricing')
        ledger.settle(rid,supplement,'Exact native receipts; conservative rate projection. No new provider call.')
    path.write_text(json.dumps(record,indent=2)+'\n')


def main(cohorts,write):
    selected=[]
    for path in sorted((LOCAL/'records').glob('*.json')):
        r=json.loads(path.read_text())
        if r.get('cohort_id') in cohorts and r.get('dispatch_intent_at'):selected.append((path,r))
    inspected=[(path,r,*inspect(r)) for path,r in selected]  # Verify all before mutation.
    ledger=Ledger(LOCAL/'stage5-ledger.sqlite',500)
    for path,r,base,proof in inspected:
        if write:apply(r,path,base,proof,ledger)
        print(json.dumps({'run':r['run_id'],'native_requests':proof['native_request_count'],'compaction_requests':len(proof['compaction_requests']),'cost':r['accounting']['estimated_cost_usd'],'complete':r['accounting']['usage_complete']}))
    if write:ledger.export(LOCAL/'stage5-ledger.json')
    ledger.db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cohort',action='append',required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();main(args.cohort,args.apply)
