"""Assemble the review packet without pooling different task cohorts."""
import csv
import datetime
import json
from collections import defaultdict
from pathlib import Path
from runtime import LOCAL


def build():
    fixed = 'stage5-long-threads'
    small_workflow = 'stage5-sol-workflow'
    final_workflow = 'stage5-final-sol-workflow'
    workflow = final_workflow if (LOCAL/('report-'+final_workflow)/'workflow.json').exists() else small_workflow
    records = [json.loads(p.read_text()) for p in (LOCAL/'records').glob('*.json')]
    records = [r for r in records if r.get('cohort_id') in [fixed, small_workflow, final_workflow]]
    flow = json.loads((LOCAL/('report-'+workflow)/'workflow.json').read_text())
    overhead = json.loads((LOCAL/'stage5-engineering-overhead.json').read_text())
    ledger = json.loads((LOCAL/'stage5-ledger.json').read_text())
    pause_path=LOCAL/'PAUSED_FOR_REVIEW.json'
    pause=json.loads(pause_path.read_text()) if pause_path.exists() else {}
    finished=(workflow==final_workflow and len([r for r in records if r['cohort_id']==final_workflow and 'grade' in r and r.get('dispatch_intent_at')])==2
              and pause.get('completed_cohort')==final_workflow and not pause.get('authorized_protocol_sha256'))
    status='The authorized stage is complete and further evaluation is paused for review.' if finished else 'The stage remains in progress until the final twelve-feature pair is complete and the review gate is restored.'
    lines = ['# Token Miser evaluation: new $500 stage', '',
             'Generated '+datetime.datetime.now(datetime.timezone.utc).isoformat()+'. '+status, '',
             'All dollars below are standard-card API-equivalent estimates of Codex Pro usage, not API-key charges or invoices. The account-wide usage of the user’s other Codex work is excluded.', '',
             '## Results', '',
             'Completed comparisons: Astra scored the same with Token Miser and cost 0.47% more across three paired tasks. The completed six-feature Sol pair scored higher and cost 5.50% less, but both arms were below $3. The final larger Sol comparison was interrupted by provider capacity and does not establish a complete cost effect.', '',
             '| Model and workload | OFF score | ON score | OFF cost | ON cost | Scope |',
             '|---|---:|---:|---:|---:|---|']
    astra = [r for r in records if r['cohort_id']==fixed and r['cell']['model']=='gpt-6-astra']
    def arm_summary(rows, on):
        arm = [r for r in rows if r['cell']['token_miser']==on]
        if not arm or any(not r.get('accounting',{}).get('usage_complete') for r in arm):
            return 'pending', 'pending'
        return f"{sum(r['success'] is True for r in arm)}/{len(arm)} tasks", f"${sum(r['accounting']['estimated_cost_usd'] for r in arm):.6f}"
    ao, ac = arm_summary(astra, False); an, anc = arm_summary(astra, True)
    lines.append(f'| Astra: three separate DeepSWE tasks | {ao} | {an} | {ac} | {anc} | Three paired tasks; OFF baselines all $3–15 |')
    arms = flow['arms']
    def workflow_arm(label):
        arm = arms.get(label)
        if not arm or arm.get('primary_score') is None:return 'pending','pending'
        cost=f"${arm['reported_cost_usd']:.6f}"+(' partial' if not arm['complete_usage'] else '') if arm['reported_cost_usd'] is not None else 'unknown'
        return f"{arm['component_passes']}/{arm['component_count']} features ({arm['agent_status']})", cost
    so, sc = workflow_arm('off'); sn, snc = workflow_arm('on')
    count=len(flow['protocol']['tasks'][0]['task_metadata']['workflow_components'])
    lines.append(f'| Sol: one workflow of {count} features | {so} | {sn} | {sc} | {snc} | One paired workflow; components are correlated |')
    paired = flow.get('paired', {})
    if 'cost_change_fraction' in paired:
        lines += ['', f"Sol workflow: observed ON-minus-OFF feature score change {paired['score_delta_on_minus_off']:+.1%}; estimated cost change {paired['cost_change_fraction']:+.2%}. This describes one pair only."]
    off_cost=arms.get('off',{}).get('reported_cost_usd')
    if off_cost is not None and arms.get('off',{}).get('complete_usage'):
        lines += ['', f"This Sol OFF baseline is {'inside' if 3<=off_cost<=15 else 'outside'} the requested $3–15 range (${off_cost:.6f}). Selection is not expanded further after this pair."]
    if any(a['agent_status'] not in (None,'completed') for a in arms.values()):
        lines+=['','The final larger Sol attempt suffered a provider capacity failure (`serverOverloaded` after HTTP503), with successful harness export and grading. It is retained as an incomplete attempt. Its cost-band membership and ON/OFF cost effect remain unknown; any submitted-code score difference is confounded by the provider failure. No completed $3–15 Sol pair has been established. The completed six-feature result below remains separate.']
    for row in records:
        if row['cohort_id'] == workflow and row.get('grade',{}).get('details'):
            detail=row['grade']['details'];label='ON' if row['cell']['token_miser'] else 'OFF'
            lines += ['', f"Sol {label}: {detail['f2p_passed']}/{detail['f2p_total']} required new checks and {detail['p2p_passed']}/{detail['p2p_total']} regression checks passed; agent status {row['agent_status']}."]
    lines += ['', 'Astra: observed score unchanged at 2/3, cost +0.46596%. The paired mean cost change is +$0.01765/task; the empirical task-bootstrap 95% interval is −$0.29793 to +$0.24523/task. Three selected tasks are too few for a reliable population conclusion. Zero discordant grades does not establish equal model performance.', '',
              'The earlier six-feature Sol OFF baseline cost $2.296652, below the requested $3 floor. Its ON cost was $2.170410 (−5.50%) and its feature score rose from 2/6 to 3/6, with complete usage. The earlier three single-task Sol baselines were only $0.59–0.75; reported ON cost was at least 14.63% higher, with one unreported interrupted Luna helper still unknown. Neither earlier cohort is silently presented as a $3–15 Sol sample. Before the six-feature ON result, one final workload of twelve distinct features was selected; its price-band membership is determined by its complete OFF cost.', '',
              flow['uncertainty'], '', '## Measured tokens', '',
              'Cumulative counts across provider requests. Reasoning is a subset of output and is priced once. Uncached input includes any cache writes; the CSVs also separate cache writes and nonreasoning output. Native Codex compaction has its own row, separate from Token Miser summaries. An audit of all sixteen native parent sessions found three compaction requests omitted by the App Server pricing snapshot; all are included here and in the conservative ledger. This corrects the earlier six-feature OFF estimate from $2.222511 to $2.296652; its ON cost is unchanged.', '',
              '| Model/workload | Mode | Usage role/model | Cached input | Uncached input | Output | Reasoning subset | Estimated cost |',
              '|---|---|---|---:|---:|---:|---:|---:|']
    grouped = defaultdict(lambda: defaultdict(float))
    for cohort in [fixed, workflow]:
        file = LOCAL/('report-'+cohort)/'token-breakdown.csv'
        if not file.exists():continue
        for row in csv.DictReader(file.open()):
            if cohort==fixed and row['requested_model']!='gpt-6-astra':continue
            key=(row['requested_model'], row['token_miser'], row['usage_role'], row['usage_model'])
            for field in ['cached_input_tokens','uncached_input_tokens','output_tokens','reasoning_tokens','estimated_cost_usd']:
                if row[field]=='':raise ValueError('Unknown usage must not become zero')
                grouped[key][field]+=float(row[field])
    for key, row in sorted(grouped.items()):
        model,on,role,usage_model=key
        counts=' | '.join(f"{int(row[k]):,}" for k in ['cached_input_tokens','uncached_input_tokens','output_tokens','reasoning_tokens'])
        lines.append(f"| {model} | {'ON' if on=='True' else 'OFF'} | {role} / {usage_model} | {counts} | ${row['estimated_cost_usd']:.6f} |")
    complete=[r for r in records if r.get('accounting',{}).get('usage_complete')]
    measured=sum(r['accounting']['estimated_cost_usd'] for r in complete)
    partial=sum(r.get('accounting',{}).get('estimated_cost_usd') or 0 for r in records if r not in complete)
    failed_usage_holds=sum(e['charged_micros'] for e in ledger['entries'] if e['status']=='uncertain')/1e6
    lines += ['', '## Budget and coverage', '',
              'One final-workflow startup attempt rejected a 36-hour input before runtime launch because the driver supports at most 24 hours. Empty profile/output/session directories, the exact validation error and source order prove zero model dispatch. That attempt is retained separately; both paid arms use the amended 24-hour allowance, without a token cap.', '',
              f"Complete trial/helper usage: **${measured:.6f}**, across {len(complete)} completed-usage records. Incomplete records, if any, retain their reservation and are not treated as zero.", '',
              f"Additional known usage from incomplete records: **${partial:.6f}**. One earlier small Sol ON helper was interrupted without final counters; its additional $90 allowance remains held. That allowance is conservative uncertainty, not a measured charge. Parent completion and grades were not changed.", '',
              f"Failed-turn uncertainty envelopes retained in the ledger: **${failed_usage_holds:.2f}**, in addition to the separate $90 helper allowance. The failed Sol parent has late, reconciled request receipts in its record, but those do not prove that every failed/retried provider request had no additional cost. No uncertainty envelope was released on that assumption.", '',
              f"Operator engineering usage observed through {overhead['captured_at']}: **${overhead['owner_measured_request_estimate_usd']:.6f}**, plus **${overhead.get('owner_reported_native_helper_cost_usd',0):.6f}** in separately retained native helpers. The active operator turn is not yet final. Jarvis evaluation-only uncertainty is bounded at $10, other helper uncertainty at $1, and the current/closing-response allowance is ${overhead['current_or_next_response_headroom_usd']}. These allowances are not measured spend.", '',
              f"Conservative admission ledger: ${ledger['charged_usd']:.6f} charged against reservations, ${ledger['reserved_usd']:.6f} still reserved, ${ledger['remaining_usd']:.6f} available under the new $500 ceiling. Settled trial charges use conservative rate bounds and can exceed the complete common-card estimate above. Engineering holds include unused future-work allowance; they are not bills.", '',
              '## Validity and limitations', '',
              '- Exact requested model IDs; high reasoning, default service and fast mode off. Account/read receipts verify ChatGPT Pro, and client thread/turn receipts clear the tier override. They do not prove an upstream invoice tier. No API-key fallback was admitted.',
              '- Real PwrAgent Electron and its pinned managed App Server run inside each native arm64 Linux task container. The driver uses lightweight budget polls, named IPC deadlines, durable usage snapshots and recursive source export. No cumulative-token cap is configured.',
              '- Unchanged hidden component verifiers run after the model stops, in pristine containers. Every selected verifier rejected the baseline and accepted its reference solution before trial admission. Both composed export/grading paths passed offline reference-solution checks. Agent code is never repaired by the evaluator.',
              '- Production PwrAgent includes the protected AGENTS.md/CLAUDE.md/SKILL.md instruction fixes. This is not a standalone synthetic-compression wrapper.',
              '- Workflow order is OFF then ON. Remote provider prompt caches are not reset by fresh containers. Generation randomness and order effects remain; no population confidence interval is justified for one workflow pair.',
              '- Native arm64 execution, task selection and the composed workflow differ from published benchmark configurations. Published costs informed selection, not the ON/OFF causal baseline.',
              '- Docker Desktop was recovered from an idle-wake failure. Its existing disk allocation grew from 56 to 96 GiB after a zero-model ENOSPC failure; no factory reset, pruning, new VM or paid cloud compute was used. The tracked UDP-kernel setting remains off to preserve the recovered working network.', '',
              '## Evidence', '']
    for title,path in [
        ('Astra and cheap Sol: detailed results',LOCAL/('report-'+fixed)/'interim.md'),
        ('Larger Sol workflow and per-component grades',LOCAL/('report-'+workflow)/'workflow.json'),
        ('Astra and cheap Sol token CSV',LOCAL/('report-'+fixed)/'token-breakdown.csv'),
        ('Larger Sol token CSV',LOCAL/('report-'+workflow)/'token-breakdown.csv'),
        ('Astra and cheap Sol paired token deltas',LOCAL/('report-'+fixed)/'paired-token-deltas.csv'),
        ('Larger Sol paired token deltas',LOCAL/('report-'+workflow)/'paired-token-deltas.csv'),
        ('Real Token Miser transformation examples',LOCAL/('report-'+workflow)/'transformation-evidence.json'),
        ('Provider duration versus full evaluator duration',LOCAL/('report-'+workflow)/'latency.csv'),
        ('Separate six-feature workflow result',LOCAL/('report-'+small_workflow)/'workflow.json'),
        ('Every provider dispatch and usage reconciliation',LOCAL/'stage5-protocol-usage-audit.json'),
        ('Native requests and compaction reconciliation',LOCAL/'stage5-native-request-audit.json'),
        ('Exact OFF provider capacity error',LOCAL/'runs/stage5-final-sol-workflow-01-twelve-feature-workflow-sol-off-infra-retry1/output/provider-failure-receipt.json'),
        ('Explicit missing usage',LOCAL/('report-'+fixed)/'missing-usage.json'),
        ('Budget ledger',LOCAL/'stage5-ledger.json'),
        ('Scoped engineering receipt',LOCAL/'stage5-engineering-receipt.json'),
        ('Scoped engineering helper receipt',LOCAL/'stage5-engineering-helper-receipt.json'),
        ('Engineering response-headroom basis',LOCAL/'stage5-engineering-headroom-proof.json')]:
        lines.append(f'- [{title}]({path})')
    lines+=['', 'Source: [draft harness PR](https://github.com/frontier-harness-eval/eval/pull/26), [headless driver PR](https://github.com/pwrdrvr/PwrAgent/pull/2707). [Official pricing](https://developers.openai.com/api/docs/pricing) was frozen in the dated repository price card. No merge/release or public agent-patch publication.', '']
    output=LOCAL/'REVIEW-stage5.md';output.write_text('\n'.join(lines))
    return output


if __name__=='__main__':
    print(build())
