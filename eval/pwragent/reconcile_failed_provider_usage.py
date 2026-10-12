"""Backfill known late usage without finalizing a failed turn or releasing holds."""
import argparse
import hashlib
import json
from accounting import CARD, cost_components
from runtime import LOCAL


def reconcile(run_id):
    path=LOCAL/'records'/(run_id+'.json');record=json.loads(path.read_text())
    if record.get('late_provider_usage_backfill'):return
    assert record['agent_status']=='failed' and not record['accounting']['usage_complete']
    receipt_path=LOCAL/'runs'/run_id/'output/parent-request-receipt.json'
    receipt=json.loads(receipt_path.read_text());assert len(receipt['turns'])==1
    turn=receipt['turns'][0];assert turn['turn_id']==record['turn_id'] and turn['model']==record['cell']['model']
    turn['terminal_event_observed']=turn['complete'];turn['complete']=False
    receipt['coverage_limitation']='A terminal event exists, but the provider outcome is failed. Reported request counters reconcile; this is not complete-cost or billing proof.'
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    parents=[r for r in record['accounting']['rows'] if r['usage_role']=='parent'];assert len(parents)==1
    parent=parents[0];old=dict(parent);tokens=turn['tokens']
    mapping={'input_tokens':'input_tokens','cached_input_tokens':'cached_input_tokens','cache_write_tokens':'cache_write_input_tokens','output_tokens':'output_tokens','reasoning_tokens':'reasoning_output_tokens'}
    assert all(tokens[native]>=parent.get(key,0) for key,native in mapping.items())
    backup=LOCAL/'record-revisions'/(run_id+'.before-late-provider-usage.json');assert not backup.exists()
    backup.write_bytes(path.read_bytes())
    parent.update({key:tokens[native] for key,native in mapping.items()})
    parent['uncached_input_tokens']=parent['input_tokens']-parent['cached_input_tokens']
    parent['nonreasoning_output_tokens']=parent['output_tokens']-parent['reasoning_tokens']
    parent['estimated_cost_usd']=turn['estimated_cost_usd']
    parent['estimated_cost_components_usd']={key:sum(r['cost_components_usd'][key] for r in turn['requests']) for key in turn['requests'][0]['cost_components_usd']}
    parent['provider_requests']=[]
    parent['provider_request_coverage_complete']=False
    parent['reported_usage_only']=True
    parent['app_catalog_refers_to_original_snapshot']=True
    rates=CARD['models'][turn['model']]
    for tier,field in [('short','projected_short_usd'),('long','projected_long_usd')]:
        parts=cost_components(parent['input_tokens'],parent['cached_input_tokens'],parent['cache_write_tokens'],parent['output_tokens'],parent['reasoning_tokens'],rates[tier])
        parent[field]=sum(parts[k] for k in ['uncached_input_excluding_writes','cached_input','cache_writes','output_including_reasoning'])
    long=rates['long'];parent['conservative_budget_usd']=(parent['uncached_input_tokens']*max(long[0],long[2])+parent['cached_input_tokens']*long[1]+parent['output_tokens']*long[3])/1e6
    account=record['accounting'];rows=account['rows']
    for total,field in [('estimated_cost_usd','estimated_cost_usd'),('projected_cost_lower_usd','projected_short_usd'),('projected_cost_upper_usd','projected_long_usd'),('conservative_budget_usd','conservative_budget_usd')]:
        account[total]=sum(r[field] for r in rows)
    record['late_provider_usage_backfill']=dict(receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        source_session_prefix_sha256=receipt['source_session_prefix_sha256'],original_parent_snapshot=old,
        reported_request_count=turn['request_count'],reservation_released_usd=0,
        explanation='Exact per-request counters reconcile to native turn totals and contain late usage absent from the app snapshot. The provider terminal failed; all costs remain partial, and the full reservation stays held. Raw results, patches and grades are unchanged.')
    path.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'run_id':run_id,'known_partial_cost_usd':account['estimated_cost_usd'],'usage_complete':False,'reservation_release':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True)
    reconcile(parser.parse_args().run_id)
