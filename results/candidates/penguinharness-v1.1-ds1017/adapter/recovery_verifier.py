"""Prepare pinned offline dependencies after the agent; run the original verifier."""
import asyncio
import hashlib
import json
import shlex
from datetime import datetime, timezone
from pathlib import Path

from harbor.verifier.verifier import Verifier

TASKS = {'filter-js-from-html', 'fix-ocaml-gc', 'large-scale-text-editing',
         'mailman', 'polyglot-c-py', 'pypi-server', 'sam-cell-seg'}


class RecoverySetupError(RuntimeError):
    pass


async def prepare(environment, task_name, bundle, expected_sha256, report_dir):
    if task_name not in TASKS:
        raise RecoverySetupError('Task outside the authorized recovery set')
    bundle = Path(bundle)
    def digest():
        with bundle.open('rb') as source:
            return hashlib.file_digest(source, 'sha256').hexdigest()
    actual = await asyncio.to_thread(digest)
    if actual != expected_sha256:
        raise RecoverySetupError('Offline dependency bundle checksum mismatch')
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot = (
        'set -eu; mkdir -p /logs/artifacts; set --; '
        'for path in /app /etc /var/lib/mailman3 /var/lib/mailman /var/spool/postfix /var/mail; '
        'do if [ -e "$path" ]; then set -- "$@" "${path#/}"; fi; done; '
        'tar --warning=no-file-changed --ignore-failed-read --exclude="var/spool/postfix/dev/*" '
        '-czf /logs/artifacts/recovery-output-before-verification.tar.gz -C / "$@"; '
        'dpkg-query -W > /logs/artifacts/recovery-installed-packages.txt'
    )
    captured = await environment.exec(snapshot, user='root', timeout_sec=240)
    if captured.return_code != 0:
        raise RecoverySetupError('Could not preserve task output before verification')
    await environment.download_file('/logs/artifacts/recovery-output-before-verification.tar.gz',
                                    report_dir / 'output-before-verification.tar.gz')
    await environment.upload_file(str(bundle), '/tmp/penguin-verifier-recovery.tar.gz')
    command = (
        'set -eu; mkdir -p /opt/verifier-recovery; '
        'tar -xzf /tmp/penguin-verifier-recovery.tar.gz -C /opt/verifier-recovery; '
        'rm /tmp/penguin-verifier-recovery.tar.gz; '
        '/bin/bash /opt/verifier-recovery/bootstrap.sh'
    )
    result = await environment.exec(command, user='root', timeout_sec=300)
    if result.return_code != 0:
        (report_dir / 'recovery-setup-error.txt').write_text((result.stdout or '') + (result.stderr or ''))
        raise RecoverySetupError('Offline dependency bootstrap failed; original tests were not run')
    marker = await environment.exec('touch /opt/verifier-recovery/.ready', user='root')
    if marker.return_code != 0:
        raise RecoverySetupError('Could not mark completed verifier preparation')
    report = {
        'prepared_at': datetime.now(timezone.utc).isoformat(), 'task_name': task_name,
        'phase': 'verification_setup_after_agent_before_test_timeout', 'bundle_sha256': expected_sha256,
        'uv_version': '0.9.5', 'test_script_modified': False,
        'assertions_modified': False, 'agent_environment_preseeded': False,
        'uv_network_access': 'offline_only',
        'installer_url': 'exact pinned uv installer URI served by a documented local bootstrap',
        'other_cached_downloads': 'exact MobileSAM weight URI and OCaml verification clone, all other curl/git calls pass through',
    }
    (report_dir / 'recovery-setup.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


class RecoveryVerifier(Verifier):
    def __init__(self, *args, recovery_bundle, recovery_bundle_sha256, **kwargs):
        super().__init__(*args, **kwargs)
        self.recovery_bundle = recovery_bundle
        self.recovery_bundle_sha256 = recovery_bundle_sha256

    async def verify(self):
        name = self.task.short_name
        proof_path = self.trial_paths.verifier_dir.parent / 'recovery/recovery-setup.json'
        if not proof_path.exists():
            raise RecoverySetupError('After-agent preparation proof is absent; refusing unprepared verification')
        proof = json.loads(proof_path.read_text())
        if proof.get('bundle_sha256') != self.recovery_bundle_sha256 or proof.get('task_name') != name:
            raise RecoverySetupError('After-agent preparation proof does not match this trial')
        marker = await self.environment.exec('test -f /opt/verifier-recovery/.ready', user='root')
        if marker.return_code != 0:
            raise RecoverySetupError('Verifier dependency preparation marker is absent')
        self.trial_paths.verifier_dir.mkdir(parents=True, exist_ok=True)
        (self.trial_paths.verifier_dir / 'recovery-setup.json').write_text(proof_path.read_text())
        path = await self.environment.exec('printf "%s" "$PATH"', user='root')
        if path.return_code != 0:
            raise RecoverySetupError('Could not resolve verifier PATH')
        self.override_env = {
            **(self.override_env or {}),
            'PATH': '/opt/verifier-recovery/shims:/root/.local/bin:' + path.stdout.strip(),
            'UV_CACHE_DIR': '/opt/verifier-recovery/cache',
            'UV_PYTHON_INSTALL_DIR': '/opt/verifier-recovery/python',
            'UV_PYTHON_PREFERENCE': 'only-managed',
            'UV_OFFLINE': '1',
        }
        # All original test files and assertions are uploaded and run by Harbor unchanged.
        result = await super().verify()
        ctrf = self.trial_paths.verifier_dir / 'ctrf.json'
        diagnostics = {'completed_at': datetime.now(timezone.utc).isoformat(),
                       'ctrf_present': ctrf.exists(), 'raw_rewards': result.rewards,
                       'recovery_setup_error': False}
        if ctrf.exists():
            try:
                diagnostics['pytest_summary'] = json.loads(ctrf.read_text()).get('results', {}).get('summary')
            except (OSError, ValueError):
                diagnostics['ctrf_parse_error'] = True
        else:
            diagnostics['requires_review'] = 'No CTRF; do not assume this zero is model failure or infrastructure failure without reviewing the log'
        (self.trial_paths.verifier_dir / 'recovery-diagnostics.json').write_text(
            json.dumps(diagnostics, indent=2) + '\n')
        return result
