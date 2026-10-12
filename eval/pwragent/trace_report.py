"""Bounded transformation evidence from exported real PwrAgent receipts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from runtime import LOCAL


def build(cohort):
    runs=[]
    fields=['objectId','toolUseId','toolName','disposition','originalCharacters',
            'replacementCharacters','retrievedCharacters','cachedReplayCount',
            'baselineParentTokens','cachedBaselineTokens','cachedRevealedTokens']
    for path in sorted((LOCAL/'records').glob('*.json')):
        record=json.loads(path.read_text())
        if record.get('cohort_id')!=cohort or not record.get('dispatch_intent_at'):continue
        receipt=LOCAL/'runs'/record['run_id']/'output/token-miser-receipt.json'
        if not receipt.exists():raise ValueError('Export the native receipt first')
        data=json.loads(receipt.read_text());objects=data['objects']
        examples=sorted(objects,key=lambda o:o.get('originalCharacters',0)-o.get('replacementCharacters',0),reverse=True)[:3]
        retrieved=next((o for o in objects if o.get('retrievedCharacters',0)>0),None)
        if retrieved and retrieved not in examples:examples.append(retrieved)
        runs.append(dict(run_id=record['run_id'],requested_on=record['cell']['token_miser'],
            effective_on=record['effective_token_miser'],native_receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
            disposition_counts=dict(Counter(o.get('disposition','unknown') for o in objects)),
            object_count=len(objects),observation_count=len(data['observations']),
            original_characters=sum(o.get('originalCharacters',0) for o in objects),
            replacement_characters=sum(o.get('replacementCharacters',0) for o in objects),
            retrieved_characters=sum(o.get('retrievedCharacters',0) for o in objects),
            cached_replays=sum(o.get('cachedReplayCount',0) for o in objects),
            examples=[{key:o[key] for key in fields if key in o} for o in examples]))
    result=dict(cohort_id=cohort,runs=runs,source='Real PwrAgent TokenMiserStore exports; no synthetic compressor.',
        interpretation='Character reductions are local transformation evidence, not net paid-token or dollar savings. Provider request counters and helper costs determine net effects. Examples selected by largest character reduction, plus one retrieval if present; no prompt or source content copied.')
    dest=LOCAL/('report-'+cohort);dest.mkdir(exist_ok=True)
    output=dest/'transformation-evidence.json';output.write_text(json.dumps(result,indent=2)+'\n')
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cohort',required=True)
    print(build(parser.parse_args().cohort))
