"""Offline preparation of the conditional longer Sol workflow; zero paid turns."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tomllib
from types import SimpleNamespace

from runtime import LOCAL, ROOT, Runtime, command, docker
from workflow import build_image, grade_workflow


def write(path, data):
    path.write_text(json.dumps(data, indent=2)+'\n')


def main():
    prior=json.loads((ROOT/'eval/pwragent/preregistered-long-threads.json').read_text())
    plan=json.loads((LOCAL/'stage5-workflow-adaptive-plan.json').read_text())
    records=[json.loads(p.read_text()) for p in (LOCAL/'records').glob('stage5-long-threads-*.json')]
    if len(records)!=12 or any('grade' not in r for r in records):
        raise RuntimeError('Finish the fixed cohort before workflow preparation')
    baselines=[r for r in records if r['cell']['model']=='gpt-6.1-sol' and not r['cell']['token_miser']]
    if len(baselines)!=3 or not all(r['accounting']['usage_complete'] and r['accounting']['estimated_cost_usd']<3 for r in baselines):
        raise RuntimeError('Conditional workload trigger not satisfied; no expansion')
    tasks=[]
    for name in plan['component_ids']:
        source=LOCAL/'cache/deep-swe/tasks'/name
        hashes={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(source.rglob('*')) if p.is_file()}
        assert hashes['instruction.md']==plan['instruction_sha256'][name]
        tasks.append(dict(id=name,suite='deep-swe',source_path=str(source),
                          source_commit=plan['source_commit'],hashes=hashes,
                          task_metadata=tomllib.loads((source/'task.toml').read_text())))
    preparation=LOCAL/'stage5-workflow-preparation';preparation.mkdir(exist_ok=True)
    draft={**prior,'tasks':tasks,'frozen_before_paid_dispatch':False}
    component_protocol=preparation/'component-preparation.json';write(component_protocol,draft)
    command([sys.executable,ROOT/'eval/pwragent/prepare_stage.py','--protocol',component_protocol],
            timeout=10800,log=preparation/'components.log')
    for task in tasks:
        proof=json.loads((LOCAL/'stage5-preparations'/task['id']/'validated.json').read_text())
        assert proof['baseline_reward']==0 and proof['oracle_reward']==1
        task['image']=proof['image']
    name='six-feature-workflow'
    existing=LOCAL/'task-builds'/(name+'-8655446')/'build.json'
    image=json.loads(existing.read_text()) if existing.exists() else build_image(tasks,name+'-8655446')
    assert image['component_ids']==plan['component_ids']
    assert image['component_image_ids']=={t['id']:t['image']['image_id'] for t in tasks}
    assert image['builder_source_sha256']==hashlib.sha256((ROOT/'eval/pwragent/workflow.py').read_bytes()).hexdigest()
    assert docker('image','inspect',image['image'],'--format','{{.Id}}').stdout.strip()==image['image_id']
    metadata=dict(metadata={'base_commit_hash':image['base_commit']},
                  agent={'timeout_sec':sum(t['task_metadata']['agent']['timeout_sec'] for t in tasks)},
                  workflow_components=tasks)
    # Exercise the exact collector/graders with no credentials, app, or model.
    fixture='fh-stage5-workflow-oracle'
    empty_auth=preparation/'empty-auth.json';write(empty_auth,{'tokens':{}})
    docker('run','-d','--name',fixture,'--platform','linux/arm64','--cpus','2','--memory','6g',
           '--network','none','--entrypoint','/usr/bin/tini',image['image'],'--','sleep','infinity')
    oracle=None
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
        fake=SimpleNamespace(name=fixture,root=preparation/'oracle',auth=empty_auth)
        oracle=grade_workflow(fake,metadata);write(preparation/'oracle-grade.json',oracle)
        assert oracle['status']=='graded' and oracle['success'], 'Composed reference export/grading failed'
    finally:
        docker('rm','-f',fixture,check=False)
    run_id='stage5-preflight-six-feature-workflow'
    inp=dict(schemaVersion=1,runId=run_id,cwd='/app',prompt='No-turn runtime preflight only.',
             model='gpt-6.1-sol',reasoningEffort='high',serviceTier='default',tokenMiser=True,
             timeoutMs=150000,runtimeManifest='/eval/runtime.json',profileDir='/eval/profile',
             codexHome='/eval/codex',preflightOnly=True)
    rt=Runtime(run_id,image['image'],inp,portable=True,seccomp=prior['seccomp_profile'])
    try:
        rt.start();proc=rt.agent();result=json.loads((rt.root/'output/result.json').read_text())
        assert proc.returncode==0 and result['status']=='completed' and not result.get('turnId')
        for line in (rt.root/'output/protocol.jsonl').read_text().splitlines():
            event=json.loads(line)
            assert not(event.get('direction')=='outbound' and event.get('method')=='turn/start')
    finally:
        rt.close()
    package=LOCAL/'workflow-packages'/name;package.mkdir(parents=True,exist_ok=True)
    prompt=['Implement the following six independent public feature requests in one coding session.',
            'The projects are under /app/parts and share one Git root at /app. Work through the projects in the listed order. Commit every completed implementation to the shared root before finishing.',
            'This is a multi-project workflow, not a published single-task benchmark. Do not access solutions, hidden verifiers, prior trial artifacts, or unrelated data. Do not launch other agents. Existing source and dependencies are provided. Passwordless sudo is available for dependencies.',
            'For the scc project use CI=1 when running its development commands. For meriyah use NODE_ENV=development.']
    for index,task in enumerate(tasks,1):
        prompt += [f"\nFeature {index}: {task['id']}\nWorking directory: /app/parts/{task['id']}",
                   Path(task['source_path'],'instruction.md').read_text()]
    (package/'instruction.md').write_text('\n\n'.join(prompt)+'\n')
    write(package/'components.json',tasks)
    task=dict(id=name,suite='deep-swe-workflow',source_path=str(package),source_commit=plan['source_commit'],
              hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in package.iterdir() if p.is_file()},
              task_metadata=metadata)
    write(preparation/'validated.json',dict(task=task,image=image,oracle_grade=oracle,
          driver_commit=prior['driver_commit'],preflight_run_id=run_id,
          preflight_result_sha256=hashlib.sha256((rt.root/'output/result.json').read_bytes()).hexdigest(),
          model_calls=0))
    print(json.dumps({'workflow_prepared':name,'model_calls':0,'oracle_success':oracle['success']}),flush=True)


if __name__=='__main__':main()
