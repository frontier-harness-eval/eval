"""Reconcile every observed parent/helper dispatch against terminal usage and pricing."""
import argparse
import hashlib
import json
from pathlib import Path
from runtime import LOCAL

COUNTERS=['inputTokens','cachedInputTokens','cacheWriteInputTokens','outputTokens',
          'reasoningOutputTokens','totalTokens']


def audit(root):
    protocol=root/'output/protocol.jsonl';result_path=root/'output/result.json'
    result=json.loads(result_path.read_text())
    requests={};thread_requests={};thread_models={};started={};terminals={};usage={};dispatch_errors=[]
    for text in protocol.read_text().splitlines():
        event=json.loads(text);envelope=event.get('envelope') or {}
        key=(event.get('backendInstance'),envelope.get('id'))
        method=envelope.get('method');params=envelope.get('params') or {}
        if event.get('direction')=='outbound' and method=='thread/start':
            thread_requests[key]=params.get('model')
        elif key in thread_requests and 'result' in envelope:
            thread=(envelope['result'] or {}).get('thread') or {}
            thread_models[thread.get('id')]=thread_requests.pop(key)
        if event.get('direction')=='outbound' and method=='turn/start':
            requests[key]=dict(thread_id=params.get('threadId'),sequence=event.get('sequence'),
                               model=params.get('model') or thread_models.get(params.get('threadId')))
        elif key in requests and ('result' in envelope or 'error' in envelope):
            request=requests.pop(key);turn=(envelope.get('result') or {}).get('turn') or {}
            if not request['thread_id'] or not turn.get('id'):
                dispatch_errors.append(request);continue
            identity=(request['thread_id'],turn['id']);started[identity]=request
        if method=='turn/completed':
            turn=params.get('turn') or {}
            terminals[(params.get('threadId'),turn.get('id'))]=turn.get('status')
        if method=='thread/tokenUsage/updated':
            usage[(params.get('threadId'),params.get('turnId'))]=(params.get('tokenUsage') or {}).get('total') or {}
    priced={};duplicates=[]
    for row in (result.get('pricing') or {}).get('lines',[]):
        if row.get('status')=='superseded':continue
        identity=(row.get('threadId'),row.get('turnId'))
        if identity in priced:duplicates.append(identity)
        priced[identity]=row
    rows=[]
    for identity,request in started.items():
        wire=usage.get(identity,{});price=priced.get(identity,{})
        differences=[key for key in COUNTERS if wire.get(key) is None or wire.get(key)!=price.get(key)]
        rows.append(dict(thread_id=identity[0],turn_id=identity[1],start_sequence=request['sequence'],
                         terminal_status=terminals.get(identity),model=price.get('model') or request.get('model'),
                         usage_line_id=price.get('usageLineId'),pricing_row_status=price.get('status'),
                         counters={key:wire.get(key) for key in COUNTERS},counter_mismatches=differences,
                         complete=terminals.get(identity)=='completed' and not differences))
    unmatched=[dict(thread_id=k[0],turn_id=k[1]) for k in priced if k not in started]
    proof=dict(schema_version=1,run_id=result['runId'],protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
               result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),turns=rows,
               unresolved_dispatches=list(requests.values())+dispatch_errors,
               duplicate_priced_turns=duplicates,priced_turns_without_observed_start=unmatched,
               all_observed_turns_reconciled=bool(rows) and all(r['complete'] for r in rows)
                   and not requests and not dispatch_errors and not duplicates and not unmatched,
               limitation='Matches all captured managed-provider starts, completed terminals, six final counters and retained pricing rows. Not billing invoices; interrupted or uncaptured usage is not assumed complete.')
    (root/'output/protocol-usage-audit.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def build(cohorts):
    rows=[]
    for file in sorted((LOCAL/'records').glob('*.json')):
        record=json.loads(file.read_text())
        if record.get('cohort_id') not in cohorts:continue
        root=LOCAL/'runs'/record['run_id']
        if not (root/'output/result.json').exists():continue
        proof=audit(root)
        rows.append(dict(run_id=record['run_id'],turns=len(proof['turns']),
                         all_observed_turns_reconciled=proof['all_observed_turns_reconciled']))
    output=LOCAL/'stage5-protocol-usage-audit.json';output.write_text(json.dumps(rows,indent=2)+'\n')
    return dict(runs=len(rows),turns=sum(r['turns'] for r in rows),
                failures=[r['run_id'] for r in rows if not r['all_observed_turns_reconciled']])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cohort',required=True,action='append')
    print(json.dumps(build(parser.parse_args().cohort)))
