"""Read-only export of real PwrAgent dispositions and helper/retrieval counters."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from runtime import LOCAL


def export(cohort=None):
    # Read approved auth solely to scrub any exact credential strings from
    # selected diagnostics. Never export/auth-copy or print this document.
    auth=json.loads(Path('/Users/huntharo/.codex/auth.json').read_text())
    secrets=[]
    def collect(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if re.search(r'token|api.?key|password|secret',k,re.I) and isinstance(v,str) and len(v)>8:secrets.append(v)
                else:collect(v)
        elif isinstance(value,list):
            for v in value:collect(v)
    collect(auth)
    def scrub(value):
        if isinstance(value,str):
            for secret in secrets:value=value.replace(secret,'[REDACTED]')
            return value
        if isinstance(value,list):return [scrub(v) for v in value]
        if isinstance(value,dict):return {k:scrub(v) for k,v in value.items() if k!='accountKey'}
        return value
    count=0
    for record in sorted((LOCAL/'records').glob('*.json')):
        row=json.loads(record.read_text())
        if cohort and row.get('cohort_id')!=cohort:continue
        if not row.get('dispatch_intent_at') or 'grade' not in row:continue
        root=LOCAL/'runs'/row['run_id'];db=root/'profile/profiles/default/state/state.db'
        if not db.exists():continue
        c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
        fields=['objectId','threadId','turnId','toolUseId','toolName','createdAt','originalCharacters','baselineParentTokens','replacementCharacters','retrievedCharacters','cachedReplayCount','cachedBaselineTokens','cachedRevealedTokens','disposition','parentModel','summary','helperUsage','groupMembers']
        objects=[]
        for (payload,) in c.execute('select payload from token_miser_objects order by created_at,object_id'):
            d=json.loads(payload);objects.append(scrub({k:d[k] for k in fields if k in d}))
        observations=[scrub(json.loads(p)) for (p,) in c.execute('select payload from token_miser_observations order by created_at,observation_id')]
        c.close()
        output={'schema_version':1,'run_id':row['run_id'],'source_db_sha256':hashlib.sha256(db.read_bytes()).hexdigest(),'source':'Real PwrAgent TokenMiserStore, read-only; no synthetic compression','objects':objects,'observations':observations}
        (root/'output/token-miser-receipt.json').write_text(json.dumps(output,indent=2)+'\n');count+=1
    print(json.dumps({'token_miser_receipt_exports':count,'model_calls':0}))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--cohort');export(p.parse_args().cohort)
