// Offline stand-in for the two pinned Git objects. Archive precisely the paths
// requested by the preparer so tests also exercise extraction, overlays and upload.
import { cpSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export function installTaskSources(root, repo, bin) {
  for (const [suite, slug] of [['terminal-bench', 'regex-log'], ['datacurve', 'httpx-multipart-response-parsing']]) {
    const definition = join(root, 'tasks', slug);
    cpSync(join(repo, 'tasks', slug), definition, { recursive: true });
    const source = join(root, 'upstream', suite === 'datacurve' ? 'tasks' : '', slug);
    cpSync(definition, source, { recursive: true });
    mkdirSync(join(source, 'environment'));
    mkdirSync(join(source, 'tests'));
    writeFileSync(join(source, 'tests/test.sh'), 'exit 0\n');
    if (suite === 'datacurve') writeFileSync(join(source, 'task.toml'), '[environment]\ndocker_image = "public.ecr.aws/test/httpx:v1.1"\n');
    else writeFileSync(join(source, 'instruction.md'), 'upstream test fixture prompt\n');
  }
  writeFileSync(join(bin, 'git'), `#!/bin/sh
case "$1:$3" in
  init:*|*:cat-file) exit 0 ;;
  *:archive)
    shift 4
    archive=$1
    shift
    case "$1" in 69671fbaac6d67a7ef0dfec016cc38a64ef7a77c|435ee89ec2f2e2289f33b0da4f992f0b7b7266b9) ;; *) exit 2;; esac
    shift
    exec tar -cf "$archive" -C "$FAKE_RUNTA_ROOT/upstream" "$@" ;;
esac
exec /usr/bin/git "$@"
`, { mode: 0o755 });
}
