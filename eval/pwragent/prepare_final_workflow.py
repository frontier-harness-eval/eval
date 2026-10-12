"""Zero-model validation for the final prospectively selected twelve-feature pair."""
import hashlib
import json
import os
import sys
import tomllib
from types import SimpleNamespace
from pathlib import Path
from runtime import LOCAL, ROOT, Runtime, command, docker
from workflow import build_image, grade_workflow
from prepare_workflow import write
from ledger import Ledger
from auth_tier_receipts import audit


def main():
    prior=json.loads((ROOT/'eval/pwragent/preregistered-sol-workflow.json').read_text())
    plan_path=ROOT/'eval/pwragent/preregistered-final-workflow-plan.json'
    plan=json.loads(plan_path.read_text())
    assert command(['git','-C',LOCAL/'cache/deep-swe','rev-parse','HEAD']).stdout.strip()==plan['source_commit']
    assert not command(['git','-C',LOCAL/'cache/deep-swe','status','--porcelain','--untracked-files=no']).stdout.strip()
    rows=[json.loads(p.read_text()) for p in (LOCAL/'records').glob('stage5-sol-workflow-*.json')]
    assert len(rows)==2 and all(r.get('accounting',{}).get('usage_complete') for r in rows), 'Finish and reconcile the current pair first'
    assert all(r.get('agent_status')=='completed' for r in rows)
    off=next(r for r in rows if not r['cell']['token_miser'])
    assert off['accounting']['estimated_cost_usd']<3
    ledger=Ledger(LOCAL/'stage5-ledger.sqlite',500)
    snapshot=ledger.snapshot();ledger.db.close()
    assert snapshot['remaining_usd']>=180, 'Both trial envelopes must fit after all existing holds'
    tasks=[]
    for name in plan['component_ids']:
        source=LOCAL/'cache/deep-swe/tasks'/name
        hashes={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(source.rglob('*')) if p.is_file()}
        assert hashes['instruction.md']==plan['instruction_sha256'][name]
        tasks.append(dict(id=name,suite='deep-swe',source_path=str(source),
                          source_commit=plan['source_commit'],hashes=hashes,
                          task_metadata=tomllib.loads((source/'task.toml').read_text())))
    assert len(tasks)==12 and len({t['id'] for t in tasks})==12
    preparation=LOCAL/'stage5-final-workflow-preparation';preparation.mkdir(exist_ok=True)
    write(preparation/'admission-envelope-before-preparation.json',snapshot)
    component_protocol=preparation/'component-preparation.json'
    write(component_protocol,{**prior,'tasks':tasks,'frozen_before_paid_dispatch':False})
    command([sys.executable,ROOT/'eval/pwragent/prepare_stage.py','--protocol',component_protocol],
            timeout=14400,log=preparation/'components.log')
    clean=[]
    for task in tasks:
        proof=json.loads((LOCAL/'stage5-preparations'/task['id']/'validated.json').read_text())
        assert proof['baseline_reward']==0 and proof['oracle_reward']==1
        task['image']=proof['image']
        status=docker('run','--rm','--network','none','--entrypoint','git',task['image']['image'],
                      '-C','/app','status','--porcelain','--untracked-files=no').stdout
        assert not status.strip(), 'Component tracked source changed'
        clean.append(dict(task=task['id'],image_id=task['image']['image_id'],tracked_clean=True))
    write(preparation/'clean-source-proof.json',clean)
    name='twelve-feature-workflow';image_record=LOCAL/'task-builds'/(name+'-8655446')/'build.json'
    image=json.loads(image_record.read_text()) if image_record.exists() else build_image(tasks,name+'-8655446')
    assert image['component_ids']==plan['component_ids']
    assert image['component_image_ids']=={t['id']:t['image']['image_id'] for t in tasks}
    assert image['builder_source_sha256']==hashlib.sha256((ROOT/'eval/pwragent/workflow.py').read_bytes()).hexdigest()
    assert docker('image','inspect',image['image'],'--format','{{.Id}}').stdout.strip()==image['image_id']
    metadata=dict(metadata={'base_commit_hash':image['base_commit']},
                  agent={'timeout_sec':sum(t['task_metadata']['agent']['timeout_sec'] for t in tasks)},
                  workflow_components=tasks)
    fixture='fh-stage5-final-workflow-oracle'
    empty_auth=preparation/'empty-auth.json';write(empty_auth,{'tokens':{}})
    docker('run','-d','--name',fixture,'--platform','linux/arm64','--cpus','2','--memory','6g',
           '--network','none','--entrypoint','/usr/bin/tini',image['image'],'--','sleep','infinity')
    try:
        docker('exec',fixture,'chown','-R',f'{os.getuid()}:{os.getgid()}','/app')
        for task in tasks:
            docker('cp',Path(task['source_path'])/'solution/solution.patch',fixture+':/tmp/component.patch')
            docker('exec','--user',f'{os.getuid()}:{os.getgid()}',fixture,'git','-C','/app',
                   'apply','--directory=parts/'+task['id'],'/tmp/component.patch')
        docker('exec',fixture,'rm','/tmp/component.patch')
        docker('exec','--user',f'{os.getuid()}:{os.getgid()}',fixture,'git','-C','/app','add','-A')
        docker('exec','--user',f'{os.getuid()}:{os.getgid()}',fixture,'git','-C','/app',
               '-c','user.name=Eval','-c','user.email=eval@localhost','commit','-qm','Reference fixture')
        oracle=grade_workflow(SimpleNamespace(name=fixture,root=preparation/'oracle',auth=empty_auth),metadata)
        write(preparation/'oracle-grade.json',oracle)
        assert oracle['status']=='graded' and oracle['success'], 'Combined reference export/grading failed'
    finally:
        docker('rm','-f',fixture,check=False)
    run_id='stage5-preflight-twelve-feature-workflow'
    inp=dict(schemaVersion=1,runId=run_id,cwd='/app',prompt='No-turn runtime preflight only.',
             model='gpt-6.1-sol',reasoningEffort='high',serviceTier='default',tokenMiser=True,
             timeoutMs=150000,runtimeManifest='/eval/runtime.json',profileDir='/eval/profile',
             codexHome='/eval/codex',preflightOnly=True)
    rt=Runtime(run_id,image['image'],inp,portable=True,seccomp=prior['seccomp_profile'])
    try:
        rt.start();proc=rt.agent();result=json.loads((rt.root/'output/result.json').read_text())
        assert proc.returncode==0 and result['status']=='completed' and not result.get('turnId')
        auth_proof=audit(rt.root)
        assert auth_proof['pro_account_receipt_verified'] and auth_proof['default_fast_off_verified']
        write(rt.root/'output/auth-tier-proof.json',auth_proof)
        for line in (rt.root/'output/protocol.jsonl').read_text().splitlines():
            event=json.loads(line);envelope=event.get('envelope') or {}
            assert not(event.get('direction')=='outbound' and (event.get('method') or envelope.get('method'))=='turn/start')
    finally:
        rt.close()
    package=LOCAL/'workflow-packages'/name;package.mkdir(parents=True,exist_ok=True)
    prompt=['Implement the following twelve distinct public feature requests in one coding session.',
            'The projects are under /app/parts and share one Git root at /app. Work through the projects in the listed order. Commit every completed implementation to the shared root before finishing.',
            'This is a multi-project workflow, not a published single-task benchmark. Do not access solutions, hidden verifiers, prior trial artifacts, or unrelated data. Do not launch other agents. Existing source and dependencies are provided. Passwordless sudo is available for dependencies.',
            'For scc use CI=1. For meriyah use NODE_ENV=development. For clack use NODE_ENV=development and NPM_CONFIG_PRODUCTION=false when running development commands.']
    for index,task in enumerate(tasks,1):
        prompt += [f"\nFeature {index}: {task['id']}\nWorking directory: /app/parts/{task['id']}",
                   Path(task['source_path'],'instruction.md').read_text()]
    (package/'instruction.md').write_text('\n\n'.join(prompt)+'\n');write(package/'components.json',tasks)
    task=dict(id=name,suite='deep-swe-workflow',source_path=str(package),source_commit=plan['source_commit'],
              hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in package.iterdir() if p.is_file()},
              task_metadata=metadata)
    write(preparation/'validated.json',dict(task=task,image=image,oracle_grade=oracle,
          driver_commit=prior['driver_commit'],preflight_run_id=run_id,
          preflight_result_sha256=hashlib.sha256((rt.root/'output/result.json').read_bytes()).hexdigest(),
          selection_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),model_calls=0))
    print(json.dumps({'workflow_prepared':name,'model_calls':0,'oracle_success':oracle['success']}),flush=True)


if __name__=='__main__':main()
