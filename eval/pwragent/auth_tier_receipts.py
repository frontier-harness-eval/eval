"""Export bounded account/tier receipts; never authentication payloads."""
import argparse
import hashlib
import json
from pathlib import Path
from runtime import LOCAL


def audit(root):
    result = json.loads((root/'output/result.json').read_text())
    protocol = root/'output/protocol.jsonl'
    requests, accounts, starts = {}, set(), []
    for line in protocol.open():
        event = json.loads(line); envelope = event.get('envelope') or {}
        key = (event.get('backendInstance'), envelope.get('id'))
        method = envelope.get('method')
        if event.get('direction') == 'outbound':
            if method == 'account/read': requests[key] = True
            if method in ['thread/start', 'turn/start']:
                params = envelope.get('params') or {}
                starts.append(dict(sequence=event.get('sequence'), method=method,
                                   model=params.get('model'), service_tier=params.get('serviceTier'),
                                   fast_mode=params.get('fastMode')))
        elif key in requests and 'result' in envelope:
            account = (envelope['result'] or {}).get('account') or {}
            accounts.add((account.get('type'), account.get('planType')))
    invalid_starts = [r for r in starts if r['service_tier'] not in [None, 'default', 'standard']
                      or r['fast_mode'] not in [None, False]]
    authenticated = accounts == {('chatgpt', 'pro')}
    effective = result.get('effectiveModelSettings') or {}
    default = (bool(starts) and not invalid_starts and result.get('serviceTier') == 'default'
               and effective.get('fastMode') is False)
    return dict(run_id=result['runId'], source_protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
                account_types=[dict(type=t, plan_type=p) for t, p in sorted(accounts)],
                pro_account_receipt_verified=authenticated, default_fast_off_verified=default,
                effective_model=effective.get('model'), effective_reasoning=effective.get('reasoningEffort'),
                requested_token_miser=result.get('tokenMiser'), effective_token_miser=result.get('effectiveTokenMiser'),
                start_requests=starts, limitation='Managed App Server account and client request receipts, not upstream billing invoices. Null serviceTier clears the client override. Account-wide quota consumption is not attributed to these tests.')


def build(cohort):
    rows = []
    for record in sorted((LOCAL/'records').glob('*.json')):
        row = json.loads(record.read_text())
        if row.get('cohort_id') != cohort or not row.get('dispatch_intent_at'): continue
        root = LOCAL/'runs'/row['run_id']
        if not (root/'output/result.json').exists(): continue
        proof = audit(root); rows.append(proof)
        (root/'output/auth-tier-proof.json').write_text(json.dumps(proof, indent=2)+'\n')
    dest = LOCAL/('report-'+cohort); dest.mkdir(exist_ok=True)
    (dest/'auth-tier-audit.json').write_text(json.dumps(rows, indent=2)+'\n')
    return dict(runs=len(rows), all_pro=all(r['pro_account_receipt_verified'] for r in rows),
                all_default_fast_off=all(r['default_fast_off_verified'] for r in rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--cohort', required=True)
    print(json.dumps(build(parser.parse_args().cohort)))
