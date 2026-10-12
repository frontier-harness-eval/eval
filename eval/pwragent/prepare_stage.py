"""No-model image, original-verifier and live export acceptance checks."""
import sys,json,pathlib,shutil,hashlib,tarfile,os,argparse
from types import SimpleNamespace
sys.path.insert(0,'eval/pwragent')
from runtime import Runtime,LOCAL,docker
from build_task import build_task
from run_stage import grade_deep
parser=argparse.ArgumentParser();parser.add_argument('--protocol',required=True)
pr=json.load(open(parser.parse_args().protocol))
current=LOCAL/'cache/current-driver'
current.unlink();current.symlink_to(pr['driver_directory'],target_is_directory=True)
for task in pr['tasks']:
    name=task['id'];source=pathlib.Path(task['source_path'])
    for relative,expected in task['hashes'].items():
        assert hashlib.sha256((source/relative).read_bytes()).hexdigest()==expected, 'Task source changed'
    dest=LOCAL/'stage5-preparations'/name;dest.mkdir(parents=True,exist_ok=True)
    proof=dest/'validated.json'
    if proof.exists():
        prior=json.load(open(proof))
        assert prior['driver_commit']==pr['driver_commit'], 'Prepared driver changed'
        assert docker('image','inspect',prior['image']['image'],'--format','{{.Id}}').stdout.strip()==prior['image']['image_id'], 'Prepared image changed'
        print(json.dumps({'event':'prepared','task':name,'resumed':True}),flush=True);continue
    build=LOCAL/'task-builds'/(name+'-8655446')/'build.json'
    print(json.dumps({'event':'build','task':name}),flush=True)
    if not build.exists():build_task(source,'fh-pwragent:8655446',name+'-8655446')
    image=json.load(open(build))
    grades={}
    for mode in ['baseline','oracle']:
        root=dest/mode;(root/'output').mkdir(parents=True,exist_ok=True);(root/'verifier').mkdir(exist_ok=True)
        patch=root/'output/patch.diff'
        patch.write_bytes(b'' if mode=='baseline' else (source/'solution/solution.patch').read_bytes())
        fake=SimpleNamespace(root=root,name='fh-stage5-'+name+'-'+mode,image=image['image'])
        grade=grade_deep(fake,source);(root/'grade.json').write_text(json.dumps(grade,indent=2)+'\n')
        assert grade['status']=='graded' and grade['success']==(mode=='oracle'),(name,mode,grade)
        grades[mode]=grade
        print(json.dumps({'event':'verifier_validated','task':name,'fixture':mode,'reward':grade['reward']}),flush=True)
    rid='stage5-preflight-'+name
    inp=dict(schemaVersion=1,runId=rid,cwd='/app',prompt='No-turn runtime preflight only.',model='gpt-6.1-sol',reasoningEffort='high',serviceTier='default',tokenMiser=True,timeoutMs=150000,runtimeManifest='/eval/runtime.json',profileDir='/eval/profile',codexHome='/eval/codex',preflightOnly=True)
    rt=Runtime(rid,image['image'],inp,portable=True,seccomp=pr['seccomp_profile'])
    try:
        rt.start()
        docker('exec','--user',f'{os.getuid()}:{os.getgid()}',rt.name,'sh','-c',"mkdir /app/fixture_directory && printf 'VALUE=7\\n' > /app/fixture_directory/main.py && ln -s main.py /app/fixture_directory/safe_relative.py && git -C /app/fixture_directory init -q && git -C /app/fixture_directory -c user.name=Eval -c user.email=eval@localhost add -A && git -C /app/fixture_directory -c user.name=Eval -c user.email=eval@localhost commit -qm fixture")
        proc=rt.agent();result=json.load(open(rt.root/'output/result.json'))
        assert proc.returncode==0 and result['status']=='completed' and result.get('preflightOnly') and not result.get('turnId'),result.get('error')
        with tarfile.open(rt.root/'output/untracked.tar.gz') as archive:
            assert archive.extractfile('fixture_directory/main.py').read()==b'VALUE=7\n'
            assert archive.getmember('fixture_directory/safe_relative.py').linkname=='main.py'
            assert not any('.git' in pathlib.Path(n).parts for n in archive.getnames())
        for line in (rt.root/'output/protocol.jsonl').read_text().splitlines():
            item=json.loads(line)
            assert not (item.get('direction')=='outbound' and item.get('method')=='turn/start')
        evidence=dict(task=name,image=image,driver_commit=pr['driver_commit'],baseline_reward=0,oracle_reward=1,preflight_run_id=rid,preflight_status=result['status'],result_sha256=hashlib.sha256((rt.root/'output/result.json').read_bytes()).hexdigest(),nested_export_checked=True)
        proof.write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps({'event':'prepared','task':name,'preflight':rid}),flush=True)
    finally:rt.close()
