"""Execute preregistered serial paired cells, retaining every admitted attempt."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from accounting import account, CARD
from build_task import build_task
from ledger import Ledger, ledger_paths
from runtime import LOCAL, ROOT, Runtime
from run_limits import run_limits

PREREG=ROOT/'eval/pwragent/preregistered-stage.json'


def write(path, value):
    Path(path).write_text(json.dumps(value,indent=2)+'\n')


def execute(args):
    protocol=Path(getattr(args,'protocol',None) or PREREG).resolve()
    protocol_hash=hashlib.sha256(protocol.read_bytes()).hexdigest() if protocol.exists() else None
    if (LOCAL/'PAUSED_FOR_REVIEW.json').exists():
        pause=json.loads((LOCAL/'PAUSED_FOR_REVIEW.json').read_text())
        if not protocol_hash or pause.get('authorized_protocol_sha256')!=protocol_hash:
            raise RuntimeError('Stage paused for explicit user review; no paid/subscription dispatch authorized')
    pr=json.loads(protocol.read_text())
    if pr.get('frozen_before_paid_dispatch') is False:
        raise RuntimeError('Draft protocol: freeze preparation evidence before dispatch')
    cohort=pr.get('cohort_id','stage1')
    ledger_db,ledger_json=ledger_paths(LOCAL,pr)
    ledger=Ledger(ledger_db,pr['stage_ceiling_usd'])
    tasks={t['id']:t for t in pr['tasks']}
    records=LOCAL/'records';records.mkdir(exist_ok=True)
    for index,cell in enumerate(pr['order']):
        for file,expected in pr.get('harness_file_sha256',{}).items():
            if hashlib.sha256((ROOT/file).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Frozen evaluator implementation changed within cohort')
        if pr.get('driver_directory') and str((LOCAL/'cache/current-driver').resolve())!=pr['driver_directory']:
            raise RuntimeError('Frozen driver directory changed within cohort')
        for file,expected in pr.get('driver_file_sha256',{}).items():
            if hashlib.sha256((LOCAL/'cache/current-driver'/file).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Frozen driver contents changed within cohort')
        if args.limit and index>=args.limit:break
        label='sol' if cell['model']=='gpt-6.1-sol' else 'astra'
        run_id=f"{cohort}-{index+1:02}-{cell['task']}-{label}-{'on' if cell['token_miser'] else 'off'}"
        record_path=records/(run_id+'.json')
        if record_path.exists():
            prior=json.loads(record_path.read_text())
            if 'grade' not in prior and 'infra_error' not in prior:
                raise RuntimeError(f'Unreconciled record {run_id}: no automatic redispatch')
            if args.retry_infra != index+1:
                continue
            if prior.get('dispatch_intent_at') or prior.get('grade',{}).get('status')!='infra_invalid':
                raise RuntimeError('Only an explicitly selected zero-dispatch infrastructure attempt may retry')
            if not any(e['run_id']==run_id and e['charged_micros']==0 and e['reserved_micros']==0 for e in ledger.snapshot()['entries']):
                raise RuntimeError('Retry requires settled zero-spend evidence')
            run_id += '-infra-retry1'
            record_path=records/(run_id+'.json')
            if record_path.exists():
                if 'grade' not in json.loads(record_path.read_text()):
                    raise RuntimeError('Unreconciled retry')
                continue
        if (LOCAL/'runs'/run_id).exists():
            raise RuntimeError(f'Unreconciled attempt {run_id}: no automatic retry')
        task=tasks[cell['task']]
        source=Path(task['source_path'])
        for name,expected in task['hashes'].items():
            if hashlib.sha256((source/name).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Task package changed after preregistration')
        image_name=cell['task']+'-8655446'
        build_json=LOCAL/'task-builds'/image_name/'build.json'
        if not build_json.exists():
            build_task(source,'fh-pwragent:8655446',image_name)
        image=json.loads(build_json.read_text())
        expected_image=pr.get('task_image_ids',{}).get(cell['task'])
        if expected_image:
            from runtime import docker
            actual_image=docker('image','inspect',image['image'],'--format','{{.Id}}').stdout.strip()
            if image['image_id']!=expected_image or actual_image!=expected_image:
                raise RuntimeError('Frozen task image changed before admission')
        # Validate driver limits before reserving budget or preparing a run.
        meta=task['task_metadata']
        limits=run_limits(pr,meta,cell['model'],protocol_hash)
        reserve=pr['reservation_usd'][cell['model']]
        if cohort=='stage1' and index<4:
            pilot_used=sum(e['charged_micros']+e['reserved_micros'] for e in ledger.snapshot()['entries'] if e['run_id'].startswith('stage1-'))/1e6
            if pilot_used+reserve>pr['pilot_ceiling_usd']:
                print(json.dumps({'event':'pause_pilot_admission','used':pilot_used,'needed':reserve}),flush=True);break
        try:ledger.reserve(run_id,reserve,'parent/helper + conservative next-call headroom')
        except ValueError as e:
            print(json.dumps({'event':'pause_budget_admission','run_id':run_id,'reason':str(e)}),flush=True);break
        ledger.export(ledger_json)
        meta=task['task_metadata']
        prompt=(source/'instruction.md').read_text()+"\n\nExecution constraints: Work only on this task. Do not launch subagents or other threads. Do not access external solutions, task verifier packages, unrelated host data, or benchmark artifacts. Passwordless sudo is available for task dependencies. Commit the task changes before finishing.\n"
        inp=dict(schemaVersion=1,runId=run_id,cwd='/app',prompt=prompt,model=cell['model'],reasoningEffort=pr['reasoning_effort'],serviceTier=pr['service_tier'],tokenMiser=cell['token_miser'],runtimeManifest='/eval/runtime.json',profileDir='/eval/profile',codexHome='/eval/codex',**limits)
        portable=cohort!='stage1' or index>=4
        seccomp=pr.get('seccomp_profile')
        if seccomp and hashlib.sha256(Path(seccomp).read_bytes()).hexdigest()!=pr['seccomp_profile_sha256']:
            raise RuntimeError('Frozen sandbox namespace profile changed')
        rt=Runtime(run_id,image['image'],inp,portable=portable,seccomp=seccomp)
        row=dict(schema_version=1,cohort_id=cohort,protocol_path=str(protocol),run_id=run_id,index=index,cell=cell,task_suite=task['suite'],source_commit=task['source_commit'],task_package_hash=hashlib.sha256(json.dumps(task['hashes'],sort_keys=True).encode()).hexdigest(),preregistration_sha256=protocol_hash,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),image=image,driver_source=str((LOCAL/'cache/current-driver').resolve().name),runtime=json.loads((LOCAL/'runtime.json').read_text()),reservation_usd=reserve)
        write(record_path,row)
        row['runtime']=json.loads((LOCAL/('runtime-portable.json' if portable else 'runtime.json')).read_text())
        row['runtime_portability']='isolated glibc 2.39 ELF interpreter/RPATH relocation; task base unchanged' if portable else 'original managed ELF'
        write(record_path,row)
        print(json.dumps({'event':'launch','run_id':run_id,'task':cell['task'],'model':cell['model'],'on':cell['token_miser'],'reserved_usd':reserve}),flush=True)
        began=time.monotonic()
        uncertain=False
        try:
            rt.start();proc=rt.agent()
            result=json.loads((rt.root/'output/result.json').read_text())
            row.update(agent_exit_code=proc.returncode,agent_status=result['status'],thread_id=result.get('threadId'),turn_id=result.get('turnId'),effective_token_miser=result.get('effectiveTokenMiser'),dispatch_intent_at=result.get('dispatchIntentAt'),error=result.get('error'))
            if result.get('dispatchIntentAt'):
                events=[json.loads(l) for l in (rt.root/'output/rollout.jsonl').read_text().splitlines() if l.strip()]
                row['accounting']=account(result,events)
                # A finalized ledger does not prove that a cancelled native
                # helper emitted a pricing row. Audit every captured dispatch.
                from protocol_usage_audit import audit as audit_provider_usage
                coverage=audit_provider_usage(rt.root)
                row['provider_usage_audit']={k:coverage[k] for k in [
                    'protocol_sha256','result_sha256','all_observed_turns_reconciled',
                    'unresolved_dispatches','duplicate_priced_turns','priced_turns_without_observed_start']}
                row['provider_usage_audit']['turn_count']=len(coverage['turns'])
                if not coverage['all_observed_turns_reconciled']:
                    row['accounting']['pricing_rows_complete']=row['accounting']['usage_complete']
                    row['accounting']['usage_complete']=False
                    row['accounting']['missing_usage']=[{
                        'thread_id':t['thread_id'],'turn_id':t['turn_id'],
                        'model':t['model'],'status':t['terminal_status'],
                        'counter_mismatches':t['counter_mismatches']}
                        for t in coverage['turns'] if not t['complete']]
                    for missing in row['accounting']['missing_usage']+coverage['unresolved_dispatches']:
                        if missing.get('model') not in CARD['models']:
                            row['accounting']['unpriced_models'].append(missing.get('model') or 'unknown_dispatched_model')
                # Native context-compaction requests can be absent from the
                # App Server display ledger. Reconcile before settling the
                # reservation; unknown native requests fail closed.
                from native_request_reconciliation import inspect as inspect_native, add_native_usage
                native_base,native_proof=inspect_native(row)
                add_native_usage(row,native_base,native_proof)
                row['token_miser_usage']=result.get('tokenMiserUsage')
                row['tool_accounting']=result.get('toolAccounting')
                row['family_pricing']=result.get('familyPricing')
                uncertain=not row['accounting']['usage_complete']
                if task['suite'].startswith('terminal'):
                    row['grade']=rt.grade_terminal(source/'tests')
                else:
                    submission=None
                    if pr.get('canonical_committed_submission'):
                        submission=rt.collect_committed_patch(meta['metadata']['base_commit_hash'])
                        row['submission_sha256']=hashlib.sha256(submission.read_bytes()).hexdigest()
                        row['submission_basis']='Original DeepSWE declared collector: git diff --binary base HEAD'
                    if meta.get('workflow_components'):
                        from workflow import grade_workflow
                        row['submission_basis']='Committed workflow root diff; original per-component diffs graded separately'
                        row['grade']=grade_workflow(rt,meta)
                    else:
                        row['grade']=grade_deep(rt,source,submission)
                row['success']=row['grade'].get('success') if result['status']=='completed' else False
                charged=row['accounting']['conservative_budget_usd']
                family=(result.get('familyPricing') or {}).get('members',[])
                if any(m.get('threadId')!=result.get('threadId') and m.get('totalCostMicros',0)>0 for m in family):
                    uncertain=True
            else:
                row['grade']={'status':'infra_invalid','success':None}
                row['success']=None;charged=0
            row['duration_seconds']=time.monotonic()-began
            ledger.settle(run_id,charged,'measured conservative token projection' if not uncertain else 'missing/incomplete usage retains reservation',uncertain=uncertain)
        except BaseException as e:
            row.update(infra_error=str(e),duration_seconds=time.monotonic()-began,success=None)
            # No automatic retry, no release without durable dispatch evidence.
            ledger.settle(run_id,0,'exception: full reservation retained',uncertain=True)
            write(record_path,row);ledger.export(ledger_json);raise
        finally:
            rt.close()
        write(record_path,row);ledger.export(ledger_json)
        if pr.get('detailed_usage_report'):
            from usage_report import build as build_usage
            build_usage(protocol)
        print(json.dumps({'event':'result','run_id':run_id,'status':row['agent_status'],'grade':row['grade'],'cost':row.get('accounting'),'ledger_remaining_usd':ledger.snapshot()['remaining_usd']}),flush=True)
        if row['success'] is None or (uncertain and (not row.get('accounting',{}).get('rows') or row['accounting'].get('unpriced_models'))):
            print(json.dumps({'event':'pause_invalid_or_uncertain','run_id':run_id}),flush=True);break
        if uncertain:
            # This is already charged at the ENTIRE reservation, rather than
            # released at the partial observed cost. The global ledger can
            # safely admit remaining fixed cells without assuming missing
            # usage is zero. Unknown model/rate or infrastructure still stops.
            print(json.dumps({'event':'quarantined_full_reservation','run_id':run_id,'charged_usd':reserve,'remaining_usd':ledger.snapshot()['remaining_usd']}),flush=True)
    if cohort!='stage1':
        write(LOCAL/'PAUSED_FOR_REVIEW.json',{'reason':'Authorized bounded cohort returned; further paid/subscription work requires explicit review','completed_cohort':cohort})


def grade_deep(rt,source,submission=None):
    from runtime import docker,mount
    patch=submission or rt.root/'output/patch.diff'
    if not patch.exists():
        return {'status':'infra_invalid','success':None,'reason':'missing exported patch'}
    name=rt.name+'-verifier'
    # No agent state, auth, profile, rollout, solution, or managed runtime mount.
    # DeepSWE declares a separate verifier with no network; dependencies are
    # already installed in the task base image. Preserve that verifier policy.
    docker('run','-d','--name',name,'--platform','linux/arm64','--user','0:0','--cpus','2','--memory','6g','--network','none','--entrypoint','/usr/bin/tini',*mount(source/'tests','/tests',True),*mount(patch,'/logs/artifacts/model.patch',True),rt.image,'--','sleep','infinity')
    try:
        docker('exec',name,'sh','-c','mkdir -p /logs/verifier && git config --global --add safe.directory /app')
        r=docker('exec','--workdir','/app',name,'bash','/tests/test.sh',timeout=1800,log=rt.root/'verifier.log',check=False)
        docker('cp',f'{name}:/logs/verifier/.',rt.root/'verifier',check=False)
        reward=rt.root/'verifier/reward.json'
        if not reward.exists():
            return {'status':'infra_invalid','success':None,'exit_code':r.returncode,'reason':'original verifier emitted no structured reward'}
        result=json.loads(reward.read_text())
        value=result.get('reward')
        return {'status':'graded' if value in (0,1) else 'infra_invalid','success':value==1 if value in (0,1) else None,'reward':value,'details':result,'exit_code':r.returncode}
    finally:docker('rm','-f',name,check=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int);p.add_argument('--retry-infra',type=int);p.add_argument('--protocol',type=Path);args=p.parse_args();execute(args)
