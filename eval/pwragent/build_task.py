"""Add identical real PwrAgent payload to the original task Dockerfile."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from runtime import LOCAL, docker


def build_task(task, payload, name):
    task = Path(task).resolve()
    context = LOCAL/'task-builds'/name
    if context.exists():
        shutil.rmtree(context)
    shutil.copytree(task/'environment',context)
    original=(context/'Dockerfile').read_text()
    overlay = '''
USER root
COPY --from=pwragent_payload /usr/local/ /usr/local/
RUN apt-get update && apt-get install -y --no-install-recommends \\
    ca-certificates git python3 sudo xvfb xauth tini dbus-x11 libsecret-1-0 \\
    libnss3 libgbm1 libxss1 libxshmfence1 \\
    $(if apt-cache show libgtk-3-0t64 >/dev/null 2>&1; then echo libgtk-3-0t64; else echo libgtk-3-0; fi) \\
    $(if apt-cache show libasound2t64 >/dev/null 2>&1; then echo libasound2t64; else echo libasound2; fi) \\
    && rm -rf /var/lib/apt/lists/*
COPY --from=pwragent_payload /opt/pwragent/ /opt/pwragent/
ENV COREPACK_HOME=/opt/task-corepack
# The PwrAgent payload supplies Corepack shims. Cache the TASK's own pinned
# manager before its offline verifier runs, also readable by the agent uid.
RUN mkdir -p /opt/task-corepack \\
    && if [ -f /app/package.json ] && node -e 'process.exit(JSON.parse(require("fs").readFileSync("/app/package.json")).packageManager ? 0 : 1)'; then corepack install; fi \\
    && chmod -R a+rX /opt/task-corepack
RUN mkdir -p /eval /app /logs/verifier && chmod 1777 /tmp \\
    && (getent passwd 501 >/dev/null || useradd -u 501 -g 20 -d /eval/profile/home -M pwreval) \\
    && echo 'pwreval ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/pwreval \\
    && chmod 0440 /etc/sudoers.d/pwreval
WORKDIR /app
'''
    (context/'Dockerfile').write_text(f'FROM {payload} AS pwragent_payload\n'+original+'\n'+overlay)
    image='fh-task:'+name
    docker('build','--platform','linux/arm64','-t',image,context,timeout=1800,log=context/'build.log')
    image_id=docker('image','inspect',image,'--format','{{.Id}}').stdout.strip()
    record={'task':task.name,'image':image,'image_id':image_id,'platform':'linux/arm64','original_dockerfile_sha256':hashlib.sha256(original.encode()).hexdigest(),'overlay_dockerfile_sha256':hashlib.sha256((context/'Dockerfile').read_bytes()).hexdigest(),'payload':payload}
    (context/'build.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('task');p.add_argument('--payload',required=True);p.add_argument('--name',required=True)
    a=p.parse_args();print(json.dumps(build_task(a.task,a.payload,a.name)))
