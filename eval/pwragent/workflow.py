"""A separately labeled multi-project workflow with original component graders.

No provider calls are made here. This is not a published single-task benchmark.
The agent sees multiple public feature requests together; original hidden verifiers
still run in separate pristine component images after the agent exits.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

from runtime import LOCAL, docker


def checked_component(component):
    name = component['id']
    if not re.fullmatch('[a-z0-9][a-z0-9-]+', name):
        raise ValueError('Invalid component path')
    image = component['image']
    if not re.fullmatch('fh-task:[a-z0-9-]+', image['image']):
        raise ValueError('Only owned prepared task images may be composed')
    actual = docker('image', 'inspect', image['image'], '--format', '{{.Id}}').stdout.strip()
    if actual != image['image_id']:
        raise ValueError('Component image changed')
    source = Path(component['source_path'])
    for path, expected in component['hashes'].items():
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('Invalid component source path')
        if hashlib.sha256((source/path).read_bytes()).hexdigest() != expected:
            raise ValueError('Component source changed')
    return name


def build_image(components, name):
    """Compose already validated images; never copy host credentials or graders."""
    if not re.fullmatch('[a-z0-9][a-z0-9-]+', name):
        raise ValueError('Invalid image name')
    names = [checked_component(c) for c in components]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate component')
    context = LOCAL/'task-builds'/name
    context.mkdir(parents=True, exist_ok=False)
    lines = []
    for index, component in enumerate(components):
        lines += [f"FROM {component['image']['image']} AS part{index}",
                  'USER root',
                  'RUN test -z "$(git -C /app ls-files --stage | awk \'$1 == 160000 {print $2}\')"',
                  'RUN git -C /app ls-files -z > /opt/workflow-tracked',
                  'RUN find /app -name .git -prune -exec rm -rf {} \\;']
    lines += [f"FROM {components[0]['image']['image']}", 'USER root',
              'RUN rm -rf /app && mkdir -p /app/parts /opt/workflow-manifests']
    for index, component in enumerate(components):
        task = component['id']
        lines += [f'COPY --from=part{index} /app/ /app/parts/{task}/',
                  f'COPY --from=part{index} /opt/workflow-tracked /opt/workflow-manifests/{task}.nul']
        if component['task_metadata']['metadata']['language'] == 'go':
            lines += [f'COPY --from=part{index} /root/go/ /root/go/']
        if component['task_metadata']['metadata']['language'] in ['javascript', 'typescript']:
            lines += [f'COPY --from=part{index} /opt/task-corepack/ /opt/task-corepack/']
    lines += ['COPY init-root.py /opt/workflow-init-root.py',
              'RUN python3 /opt/workflow-init-root.py', 'WORKDIR /app']
    (context/'Dockerfile').write_text('\n'.join(lines)+'\n')
    init = '''import os,pathlib,subprocess
root=pathlib.Path('/app')
def git(*args):return subprocess.run(['git','--literal-pathspecs','-C',str(root),*args],check=True,capture_output=True)
git('init','-q');git('config','core.hooksPath','/dev/null')
paths=[]
for manifest in sorted(pathlib.Path('/opt/workflow-manifests').glob('*.nul')):
    name=manifest.stem
    for path in manifest.read_bytes().split(b'\\0'):
        if not path:continue
        relative=pathlib.PurePosixPath(os.fsdecode(path))
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe original path')
        paths.append(os.fsencode('parts/'+name+'/')+path)
index=pathlib.Path('/opt/workflow-pathspec.nul');index.write_bytes(b'\\0'.join(paths)+b'\\0')
git('add','-f','--pathspec-from-file='+str(index),'--pathspec-file-nul')
env=os.environ.copy();env.update(GIT_AUTHOR_DATE='2026-10-12T00:00:00Z',GIT_COMMITTER_DATE='2026-10-12T00:00:00Z')
subprocess.run(['git','-C',str(root),'-c','user.name=Eval','-c','user.email=eval@localhost','commit','-qm','Pinned public component snapshots'],env=env,check=True)
'''
    (context/'init-root.py').write_text(init)
    image = 'fh-task:'+name
    docker('build', '--platform', 'linux/arm64', '-t', image, context,
           timeout=1800, log=context/'build.log')
    for component in components:
        checked_component(component)
    image_id = docker('image', 'inspect', image, '--format', '{{.Id}}').stdout.strip()
    base = docker('run', '--rm', '--entrypoint', 'git', image,
                  '-C', '/app', 'rev-parse', 'HEAD').stdout.strip()
    record = dict(image=image, image_id=image_id, base_commit=base,
                  component_ids=names, platform='linux/arm64',
                  component_image_ids={c['id']:c['image']['image_id'] for c in components},
                  builder_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  dockerfile_sha256=hashlib.sha256((context/'Dockerfile').read_bytes()).hexdigest(),
                  init_root_sha256=hashlib.sha256(init.encode()).hexdigest())
    (context/'build.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def component_patch(rt, base, component):
    name = checked_component(component)
    if not re.fullmatch('[0-9a-f]{40}', base):
        raise ValueError('Invalid workflow base')
    patch = docker('exec', '--user', f'{os.getuid()}:{os.getgid()}', rt.name,
                   'git', '-C', '/app', 'diff', '--binary',
                   '--relative=parts/'+name, base, 'HEAD', '--', 'parts/'+name).stdout
    # Same credential withholding as the canonical root submission collector.
    auth = json.loads(Path(rt.auth).read_text())
    secrets = [v for v in (auth.get('tokens') or {}).values() if isinstance(v, str) and len(v) >= 8]
    if any(secret in patch for secret in secrets):
        raise RuntimeError('Credential detected in component submission; artifact withheld')
    root = rt.root/'components'/name
    root.mkdir(parents=True, exist_ok=True); (root/'verifier').mkdir(exist_ok=True)
    target = root/'submission.patch'; target.write_text(patch); target.chmod(0o600)
    return target


def grade_workflow(rt, metadata):
    from run_stage import grade_deep
    results = []
    for index, component in enumerate(metadata['workflow_components']):
        patch = component_patch(rt, metadata['metadata']['base_commit_hash'], component)
        fake = SimpleNamespace(root=patch.parent, name=rt.name+'-c'+str(index),
                               image=component['image']['image'])
        grade = grade_deep(fake, Path(component['source_path']), patch)
        results.append(dict(task=component['id'], grade=grade,
                            submission_sha256=hashlib.sha256(patch.read_bytes()).hexdigest()))
    valid = all(r['grade']['status'] == 'graded' for r in results)
    passed = sum(r['grade'].get('success') is True for r in results)
    strict = passed == len(results) if valid else None
    details = dict(component_total=len(results), component_passed=passed,
                   component_fraction=passed/len(results) if valid else None,
                   statistical_unit='One multi-project thread; components are not independent trials')
    for group in ['f2p', 'p2p']:
        total = sum(r['grade'].get('details', {}).get(group+'_total', 0) for r in results)
        good = sum(r['grade'].get('details', {}).get(group+'_passed', 0) for r in results)
        details.update({group+'_total':total, group+'_passed':good,
                        group:good/total if valid and total else None})
    return dict(status='graded' if valid else 'infra_invalid', success=strict,
                reward=int(strict) if strict is not None else None,
                details=details, components=results)
