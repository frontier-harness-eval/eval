"""Assemble one published task from repository prompts and immutable upstream assets."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

SOURCES = {
    "terminal-bench": ("https://github.com/laude-institute/terminal-bench-2.git",
                       "69671fbaac6d67a7ef0dfec016cc38a64ef7a77c"),
    "datacurve": ("https://github.com/datacurve-ai/deep-swe.git",
                  "435ee89ec2f2e2289f33b0da4f992f0b7b7266b9"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_source(suite, task, cache, deep_swe, staging):
    url, revision = SOURCES[suite]
    repo = cache / (suite + ".git")
    if suite == "datacurve" and deep_swe.exists():
        repo = deep_swe
    elif not repo.exists():
        subprocess.run(["git", "init", "--bare", "--quiet", str(repo)], check=True)
    git = ["git", "-C", str(repo)]
    if subprocess.run([*git, "cat-file", "-e", revision + "^{commit}"], stderr=subprocess.DEVNULL).returncode:
        if repo == deep_swe:
            raise ValueError(f"{repo} lacks the pinned DeepSWE commit {revision}")
        subprocess.run([*git, "fetch", "--quiet", "--depth=1", url, revision], check=True)
    path = ("tasks/" if suite == "datacurve" else "") + task
    archive = staging / "source.tar"
    files = [f"{path}/{name}" for name in ("environment", "tests", "instruction.md", "task.toml")]
    subprocess.run([*git, "archive", "-o", str(archive), revision, *files], check=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(staging)], check=True)
    return staging / path


def deep_swe_metadata(source, repo_prompt):
    text = (source / "task.toml").read_text()
    if (source / "instruction.md").read_bytes() == repo_prompt.read_bytes():
        return text
    # Three published prompts omit the upstream instruction to commit. Collect the
    # final workspace against the same base without changing the agent's Git index.
    collect = tomllib.loads(text)["verifier"]["collect"]
    original = collect[0]["command"]
    match = re.search(r"git diff --binary ([0-9a-f]{40}) HEAD > /logs/artifacts/model.patch", original)
    if len(collect) != 1 or not match:
        raise ValueError(f"Unrecognized DeepSWE patch collector for {source.name}")
    base = match.group(1)
    command = ("set -e; cd /app; mkdir -p /logs/artifacts; git config --global --add safe.directory /app; "
               'task_index=$(mktemp /tmp/fh-model-index.XXXXXX); rm -f "$task_index"; trap \'rm -f "$task_index"\' EXIT; export GIT_INDEX_FILE="$task_index"; '
               f"git read-tree {base}; git add -A; git diff --cached --binary {base} > /logs/artifacts/model.patch")
    old = "command = " + json.dumps(original)
    if text.count(old) != 1:
        raise ValueError(f"Ambiguous DeepSWE patch collector for {source.name}")
    return text.replace(old, "command = " + json.dumps(command), 1)


def prepare_source_bundle(cache, destination):
    """Supply the offline repository referenced by the published Cython prompt."""
    repo = cache / "pyknotid.git"
    revision = "441c807dbec2ee32e1da572e24e58d52a4eb7afa"
    tag = "refs/tags/0.5.3"
    if not repo.exists():
        subprocess.run(["git", "init", "--bare", "--quiet", str(repo)], check=True)
    git = ["git", "-C", str(repo)]
    if subprocess.run([*git, "show-ref", "--verify", "--quiet", tag]).returncode:
        subprocess.run([*git, "fetch", "--quiet", "--no-tags", "https://github.com/SPOCKnots/pyknotid.git",
                        f"{tag}:{tag}"], check=True)
    actual = subprocess.check_output([*git, "rev-parse", tag + "^{commit}"], text=True).strip()
    if actual != revision:
        raise ValueError("The public source tag does not match the benchmark revision")
    branch = "refs/heads/source-0.5.3"
    subprocess.run([*git, "update-ref", branch, revision], check=True)
    subprocess.run([*git, "symbolic-ref", "HEAD", branch], check=True)
    subprocess.run([*git, "bundle", "create", str(destination), "HEAD", branch, tag], check=True)


def prepare(task_id, repo_tasks, output, cache, deep_swe):
    suite, slug = task_id.split("/", 1)
    if suite not in SOURCES or not re.fullmatch(r"[\w-]+", slug, re.ASCII):
        raise ValueError(f"Invalid task ID {task_id}")
    authority = repo_tasks / slug
    if tomllib.loads((authority / "task.toml").read_text())["task"]["name"] != task_id:
        raise ValueError(f"Task identity mismatch for {task_id}")
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with (cache / ".prepare.lock").open("a") as lock, tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        fcntl.flock(lock, fcntl.LOCK_EX)
        staging = Path(tmp)
        source = export_source(suite, slug, cache, deep_swe, staging)
        prompt = authority / "instruction.md"
        upstream_prompt = digest(source / "instruction.md")
        if suite == "datacurve":
            metadata = deep_swe_metadata(source, prompt)
            (source / "task.toml").write_text(metadata)
        else:
            shutil.copyfile(authority / "task.toml", source / "task.toml")
        shutil.copyfile(prompt, source / "instruction.md")
        if task_id == "terminal-bench/build-cython-ext":
            prepare_source_bundle(cache, source / "pyknotid.bundle")
        hashes = {str(p.relative_to(source)): digest(p) for p in sorted(source.rglob("*")) if p.is_file()}
        record = {"id": task_id, "commit": SOURCES[suite][1], "upstream_instruction_sha256": upstream_prompt,
                  "repo_instruction_sha256": digest(prompt), "files_sha256": hashes}
        (source / "input-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        source.rename(output)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task")
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo-tasks", type=Path, default=Path("tasks"))
    parser.add_argument("--cache", type=Path, default=Path(".fh-local/sources"))
    parser.add_argument("--deep-swe", type=Path, default=Path(".fh-local/deep-swe"))
    args = parser.parse_args()
    try:
        prepare(args.task, args.repo_tasks, args.output.resolve(), args.cache.resolve(), args.deep_swe.resolve())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Task preparation failed: {error}\n")
