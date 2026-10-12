"""Report the preregistered long-thread metric without pooling components as trials."""
import argparse
import json
from pathlib import Path
from runtime import LOCAL
from usage_report import build as usage_report
from cost_band_report import build as band_report


def build(protocol):
    pr=json.loads(Path(protocol).read_text())
    component_count=len(pr['tasks'][0]['task_metadata']['workflow_components'])
    rows=[json.loads(p.read_text()) for p in sorted((LOCAL/'records').glob('*.json'))]
    rows=[r for r in rows if r.get('cohort_id')==pr['cohort_id']]
    zero_dispatch=[r for r in rows if r.get('zero_dispatch_reconciliation')]
    rows=[r for r in rows if r not in zero_dispatch]
    arms={}
    for row in rows:
        label='on' if row['cell']['token_miser'] else 'off'
        if label in arms:raise ValueError('Duplicate workflow arm; repeats must be specified separately')
        grade=row.get('grade') or {};details=grade.get('details') or {};account=row.get('accounting') or {}
        arms[label]=dict(run_id=row['run_id'],agent_status=row.get('agent_status'),
                         component_passes=details.get('component_passed'),
                         component_count=details.get('component_total'),
                         primary_score=details.get('component_fraction'),
                         whole_thread_success=row.get('success'),
                         complete_usage=account.get('usage_complete',False),
                         reported_cost_usd=account.get('estimated_cost_usd'),
                         cost_upper_usd=account.get('estimated_cost_usd') if account.get('usage_complete') else row['reservation_usd'],
                         components=grade.get('components',[]))
        passed=details.get('component_passed')
        arms[label]['cost_per_verified_feature_usd']=(account['estimated_cost_usd']/passed
            if passed and account.get('usage_complete') and account.get('estimated_cost_usd') is not None else None)
    paired={}
    if set(arms)=={'off','on'}:
        off,on=arms['off'],arms['on'];scores=[off['primary_score'],on['primary_score']]
        paired['thread_pairs_with_valid_score']=int(all(x is not None for x in scores))
        paired['normally_completed_pairs']=int(off['agent_status']=='completed' and on['agent_status']=='completed')
        paired['score_delta_on_minus_off']=scores[1]-scores[0] if all(x is not None for x in scores) else None
        if off['complete_usage'] and on['complete_usage']:
            paired['cost_delta_on_minus_off_usd']=on['reported_cost_usd']-off['reported_cost_usd']
            paired['cost_change_fraction']=on['reported_cost_usd']/off['reported_cost_usd']-1
    result=dict(schema_version=1,cohort_id=pr['cohort_id'],primary_metric=pr['analysis']['primary_correctness'],
                uncertainty=f'One paired workflow. Its {component_count} components are correlated within each shared model thread and are not independent experiments. This is a descriptive result; no population-effect confidence interval is justified.',
                comparability=f'New workflow of {component_count} features, separate from other cohorts and published leaderboards. Original component verifiers are unchanged.',
                billing='Codex Pro usage, priced at the frozen standard API card for comparison. Not API-key charges or billing invoices. Reasoning is included in output.',
                arms=arms,paired=paired,protocol=pr,zero_dispatch_infrastructure_attempts=zero_dispatch)
    dest=LOCAL/('report-'+pr['cohort_id']);dest.mkdir(exist_ok=True)
    (dest/'workflow.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Longer Sol workflow: Token Miser OFF/ON','',result['comparability'],'',result['billing'],'',
           '| Arm | Features passed | Primary score | All features passed and completed | Estimated cost | Cost per verified feature |',
           '|---|---:|---:|---|---:|---:|']
    for label in ['off','on']:
        arm=arms.get(label,{})
        score=arm.get('primary_score');cost=arm.get('reported_cost_usd');per=arm.get('cost_per_verified_feature_usd')
        passed=arm.get('component_passes');whole=arm.get('whole_thread_success')
        cost_text=(f'${cost:.4f}'+(' (partial)' if not arm.get('complete_usage') else '')) if cost is not None else 'unknown/pending'
        lines.append('| '+label.upper()+' | '+(str(passed) if passed is not None else 'pending')+'/'+str(arm.get('component_count') or component_count)+' | '+(f'{score:.1%}' if score is not None else 'pending')+' | '+(str(whole) if whole is not None else 'pending')+' | '+cost_text+' | '+(f'${per:.4f}' if per is not None else 'undefined/pending')+' |')
    if any(a['agent_status'] not in (None,'completed') for a in arms.values()):
        lines+=['','At least one parent failed or was interrupted. Its submitted-code grade is retained, but the realized score difference is confounded by incomplete execution. This is not a completed efficacy or complete-cost pair.']
    lines+=['',result['uncertainty'],'','The token-breakdown and paired-token-deltas files contain cached input, uncached input, output, reasoning, and separate summary-model rows. Missing usage remains unknown with its reservation retained.']
    (dest/'workflow.md').write_text('\n'.join(lines)+'\n')
    usage_report(protocol);band_report(protocol)
    return dest/'workflow.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--protocol',required=True,type=Path)
    print(build(parser.parse_args().protocol))
