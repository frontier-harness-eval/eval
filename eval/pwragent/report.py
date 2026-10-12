"""Produce an interim paired report without silently dropping failed cells."""
import json
import math
from pathlib import Path
import random
import statistics
import argparse
from runtime import LOCAL,ROOT
from ledger import ledger_paths


def interval(values,seed=20261011):
    if not values:return None
    rng=random.Random(seed)
    samples=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(10000))
    return [samples[249],samples[9749]]


def verifier_scores(records):
    """Task-weighted diagnostics; raw check fractions do not replace pass@1."""
    valid=[r for r in records if r.get('success') is not None]
    output={'scope':'Original verifier fractions, equal weight per task attempt; independent of completion/budget gate. Individual checks are not independent tasks.'}
    for key in ['f2p','p2p','partial']:
        values=[r.get('grade',{}).get('details',{}).get(key) for r in valid]
        values=[v for v in values if isinstance(v,(int,float)) and not isinstance(v,bool)]
        output[key]={'task_attempts_with_score':len(values),'mean':statistics.mean(values) if values else None}
    output['noncompleted_agent_attempts']=sum(r.get('agent_status')!='completed' for r in valid)
    return output


def cost_direction(bounds):
    if bounds[0]>0:return 'higher'
    if bounds[1]<0:return 'lower'
    if bounds==[0,0]:return 'equal_observed'
    return 'unresolved'


def build(paused=False,protocol=None):
    pr=json.loads(Path(protocol or ROOT/'eval/pwragent/preregistered-stage.json').read_text())
    cohort=pr.get('cohort_id','stage1')
    records=[json.loads(f.read_text()) for f in sorted((LOCAL/'records').glob('*.json'))]
    selected_cohorts=pr.get('record_cohort_ids',[cohort])
    records=[r for r in records if r.get('cohort_id','stage1') in selected_cohorts]
    summary={'schema_version':1,'cohort_id':cohort,'stage':'paused pending explicit review' if paused else 'collecting within bounded stage','preregistration':pr,'ledger':json.loads(ledger_paths(LOCAL,pr)[1].read_text()),'models':{},'records':records}
    summary['executed_suites']=sorted({r['task_suite'] for r in records if r.get('dispatch_intent_at')})
    summary['unexecuted_cells']=[c for c in summary['preregistration']['order'] if not any(r['cell']==c and r.get('dispatch_intent_at') for r in records)]
    summary['record_cohort_ids']=selected_cohorts
    summary['overhead']={name:json.loads((LOCAL/name).read_text()) for name in pr.get('overhead_snapshot_files',['overhead-snapshot.json','jarvis-overhead-snapshot.json']) if (LOCAL/name).exists()}
    summary['raw_usage_totals']={k:sum(line.get(k,0) for r in records for line in r.get('accounting',{}).get('rows',[])) for k in ['input_tokens','uncached_input_tokens','cached_input_tokens','cache_write_tokens','output_tokens','reasoning_tokens']}
    summary['reported_task_cost_usd']=sum(r.get('accounting',{}).get('estimated_cost_usd',0) or 0 for r in records)
    for model in summary['preregistration']['models']:
        rows=[r for r in records if r['cell']['model']==model]
        arms={}
        for arm,label in [(False,'off'),(True,'on')]:
            a=[r for r in rows if r['cell']['token_miser']==arm]
            valid=[r for r in a if r.get('success') is not None]
            pending=[r for r in a if 'grade' not in r and 'infra_error' not in r]
            costs=[r['accounting']['estimated_cost_usd'] for r in a if r.get('accounting',{}).get('usage_complete') and r['accounting'].get('estimated_cost_usd') is not None]
            total=sum(costs)
            passed=sum(r.get('success') is True for r in valid)
            arms[label]=dict(attempted=len(a),pending=len(pending),graded_valid=len(valid),infra_invalid=len(a)-len(valid)-len(pending),passes=passed,pass_at_1=passed/len(valid) if valid else None,costed_runs=len(costs),api_equivalent_cost_usd=total,mean_cost_per_attempt_usd=statistics.mean(costs) if costs else None,cost_per_resolved_task_usd=total/passed if passed and len(costs)==len(a) else None)
            arms[label]['verifier_numeric_diagnostics']=verifier_scores(a)
        by_task={}
        for r in rows:
            pair=by_task.setdefault(r['cell']['task'],{})
            arm=r['cell']['token_miser']
            if arm not in pair or r.get('success') is not None:
                pair[arm]=r
        pairs=[(t,p[False],p[True]) for t,p in by_task.items() if set(p)=={False,True} and all(r.get('success') is not None for r in p.values())]
        diffs=[int(on['success'])-int(off['success']) for _,off,on in pairs]
        wins=sum(x==1 for x in diffs);losses=sum(x==-1 for x in diffs);discord=wins+losses
        pvalue=min(1,2*sum(math.comb(discord,k) for k in range(min(wins,losses)+1))/2**discord) if discord else 1
        cost_pairs=[(off['accounting']['estimated_cost_usd'],on['accounting']['estimated_cost_usd']) for _,off,on in pairs if off.get('accounting',{}).get('usage_complete') and on.get('accounting',{}).get('usage_complete') and all(r['accounting'].get('estimated_cost_usd') is not None for r in [off,on])]
        cost_diffs=[on-off for off,on in cost_pairs]
        paired=dict(n=len(pairs),score_delta_on_minus_off=statistics.mean(diffs) if diffs else None,score_delta_bootstrap_95_ci=interval(diffs),on_only_pass=wins,off_only_pass=losses,exact_mcnemar_p=pvalue,zero_discordance_one_sided_95_upper_probability=(1-.05**(1/len(pairs))) if pairs and not discord else None,cost_pairs=len(cost_pairs),mean_cost_delta_on_minus_off_usd=statistics.mean(cost_diffs) if cost_diffs else None,cost_delta_bootstrap_95_ci_usd=interval(cost_diffs),aggregate_cost_change_fraction=(sum(b for a,b in cost_pairs)/sum(a for a,b in cost_pairs)-1) if cost_pairs and sum(a for a,b in cost_pairs)>0 else None)
        paired.update(off_passes=sum(off['success'] for _,off,on in pairs),on_passes=sum(on['success'] for _,off,on in pairs))
        without_ipc=[(off,on) for _,off,on in pairs if not any(r.get('failure_classification',{}).get('infrastructure_trigger') for r in [off,on])]
        paired['evaluator_interruptions']={'affected_pairs':len(pairs)-len(without_ipc),'pairs_without_identified_evaluator_interruption':len(without_ipc),'off_passes_without_interruption':sum(off['success'] for off,on in without_ipc),'on_passes_without_interruption':sum(on['success'] for off,on in without_ipc),'limitation':'Primary completion-gated score retains every failure. This secondary diagnostic separates identified evaluator IPC interruptions; it is not a replacement score or an unbiased missing-outcome correction.'}
        paired['verifier_numeric_diagnostics']={}
        for key in ['f2p','p2p','partial']:
            values=[]
            for _,off,on in pairs:
                scores=[r.get('grade',{}).get('details',{}).get(key) for r in [off,on]]
                if all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in scores):values.append(scores[1]-scores[0])
            paired['verifier_numeric_diagnostics'][key]={'pairs_with_scores':len(values),'mean_on_minus_off':statistics.mean(values) if values else None,'bootstrap_95_ci':interval(values)}
        for arm,label in [(False,'off'),(True,'on')]:
            scored=[off if not arm else on for _,off,on in pairs]
            lower=sum(r['accounting']['estimated_cost_usd'] for r in scored)
            upper=sum(r['accounting']['estimated_cost_usd'] if r['accounting']['usage_complete'] else r['reservation_usd'] for r in scored)
            passes=paired[label+'_passes']
            paired['valid_grade_reported_cost_per_resolved_'+label+'_usd']=lower/passes if passes else None
            paired['valid_grade_cost_per_resolved_'+label+'_possible_interval_usd']=[lower/passes,upper/passes] if passes else None
        # Preserve failed/cancelled pairs in cost bounds. Complete-price pairs
        # are a secondary coverage statistic, not an efficacy subset.
        finance_pairs=[(p[False],p[True]) for p in by_task.values() if set(p)=={False,True} and all(r.get('dispatch_intent_at') for r in p.values())]
        observed_pairs=[(off,on) for off,on in finance_pairs if all(r.get('accounting',{}).get('estimated_cost_usd') is not None for r in [off,on])]
        if observed_pairs:
            observed_off=sum(off['accounting']['estimated_cost_usd'] for off,on in observed_pairs)
            observed_on=sum(on['accounting']['estimated_cost_usd'] for off,on in observed_pairs)
            upper_off=sum(off['accounting']['estimated_cost_usd'] if off['accounting']['usage_complete'] else off['reservation_usd'] for off,on in observed_pairs)
            upper_on=sum(on['accounting']['estimated_cost_usd'] if on['accounting']['usage_complete'] else on['reservation_usd'] for off,on in observed_pairs)
            paired.update(all_pairs_reported_cost_n=len(observed_pairs),reported_cost_off_usd=observed_off,reported_cost_on_usd=observed_on,reported_cost_change_fraction=observed_on/observed_off-1 if observed_off else None,uncertain_cost_pairs=sum(not(off['accounting']['usage_complete'] and on['accounting']['usage_complete']) for off,on in observed_pairs),possible_total_cost_delta_interval_usd=[observed_on-upper_off,upper_on-observed_off],reported_cost_limitation='Provider-reported snapshot estimate; cancelled in-flight usage can be missing. Full unknown reservations remain charged. No API billing invoice.')
            paired['sample_cost_direction_with_missing_usage_bounds']=cost_direction(paired['possible_total_cost_delta_interval_usd'])
            paired['reported_cost_delta_bootstrap_95_ci_usd']=interval([on['accounting']['estimated_cost_usd']-off['accounting']['estimated_cost_usd'] for off,on in observed_pairs])
            paired['finance_pairs_with_invalid_grade']=sum(off.get('success') is None or on.get('success') is None for off,on in observed_pairs)
            for label,lower,upper in [('off',observed_off,upper_off),('on',observed_on,upper_on)]:
                passed=paired[label+'_passes']
                paired['reported_cost_per_resolved_'+label+'_usd']=lower/passed if passed and len(observed_pairs)==len(pairs) else None
                paired['cost_per_resolved_'+label+'_possible_interval_usd']=[lower/passed,upper/passed] if passed and len(observed_pairs)==len(pairs) else None
        summary['models'][model]={'arms':arms,'paired':paired}
    dest=LOCAL/('report' if cohort=='stage1' else 'report-'+cohort);dest.mkdir(exist_ok=True)
    (dest/'interim.json').write_text(json.dumps(summary,indent=2)+'\n')
    (dest/'records.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in records))
    md=['# PwrAgent Token Miser interim evaluation — '+cohort,'', 'Further paid/subscription eval model work is paused pending explicit user review approval.' if paused else f"Collection is in progress under the inclusive ${pr['stage_ceiling_usd']} cumulative ceiling.",'', '| Model | OFF passes | ON passes | Valid score pairs | ON−OFF score | Reported ON/OFF cost |', '|---|---:|---:|---:|---:|---:|']
    for model,s in summary['models'].items():
        a=s['arms'];p=s['paired'];delta=p['score_delta_on_minus_off'];cost=p.get('reported_cost_change_fraction')
        md.append(f"| {model} | {p['off_passes']}/{p['n']} | {p['on_passes']}/{p['n']} | {p['n']} | {delta*100:.1f} pp | {cost*100:+.2f}% |" if delta is not None and cost is not None else f"| {model} | {p['off_passes']}/{p['n']} | {p['on_passes']}/{p['n']} | {p['n']} | unresolved | unresolved |")
    if any(s['arms'][label]['verifier_numeric_diagnostics']['partial']['task_attempts_with_score'] for s in summary['models'].values() for label in ['off','on']):
        md.extend(['','Original verifier numeric scores (equal weight per task attempt; separate from completion/budget-gated task success):','','| Model | Arm | New checks passed | Regression checks passed | All checks passed |','|---|---|---:|---:|---:|'])
        for model,s in summary['models'].items():
            for label in ['off','on']:
                scores=s['arms'][label]['verifier_numeric_diagnostics']
                values=[f"{scores[k]['mean']*100:.2f}%" if scores[k]['mean'] is not None else 'unavailable' for k in ['f2p','p2p','partial']]
                md.append('| '+model+' | '+label+' | '+' | '.join(values)+' |')
    incomplete=any(r.get('dispatch_intent_at') and not r.get('accounting',{}).get('usage_complete') for r in records)
    cost_note='Missing cancellation usage requires the reported cost bounds; direction is unresolved when they include zero. Full unknown reservations remain charged.' if incomplete else 'All dispatched cells in this cohort have complete reported usage. Cost direction describes these observed pairs, not a population effect.'
    md.extend(['', 'Cost percentages use all financial pairs, including infrastructure-invalid grades and cancelled runs when present. Score uses valid graded pairs. '+cost_note+' See interim.json for both paired counts, bootstrap intervals, McNemar and finite-sample discordance bounds. A zero-width empirical bootstrap is not proof of equality.'])
    md.extend(['','Costs are API-equivalent estimates for Codex subscription execution, not verified API-credit invoices. The ledger uses a higher conservative projection for admission and keeps unknown spend reserved. Reasoning is included in output; native helper and retrieval rows are retained.','', 'This uses own matched pairs in native Linux arm64 containers, not SWE-bench Verified or the published Kimi/amd64 FrontierHarness leaderboard configuration. Executed suites and unexecuted cells are listed explicitly in interim.json; each cohort uses only its own preregistered task packages. Sample selection, order, hashes, exact commits, pricing snapshot, failures and confidence intervals are in interim.json. A small sample does not establish population-level improvement.','', 'Historical GPT-5.6-Sol host pilots are auxiliary, non-efficacy-grade evidence. They are not pooled with these requested-model results.','', 'Budget ledger: '+json.dumps({k:v for k,v in summary['ledger'].items() if k!='entries'})])
    (dest/'interim.md').write_text('\n'.join(md)+'\n')
    print(json.dumps({'report':str(dest/'interim.json'),'models':summary['models'],'ledger':{k:v for k,v in summary['ledger'].items() if k!='entries'}},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--paused',action='store_true');p.add_argument('--protocol',type=Path);args=p.parse_args();build(args.paused,args.protocol)
