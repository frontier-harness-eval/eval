"""Keep Pier's native evidence mounts alongside the mcode and Runta CA mounts."""

from pier.environments.docker.docker import DockerEnvironment


class Environment(DockerEnvironment):
    def __init__(self, *args, mounts_json=None, **kwargs):
        # Pier treats supplied mounts as a replacement. Extend its own defaults
        # so CA/session persistence does not remove official verifier evidence.
        super().__init__(*args, mounts_json=mounts_json, **kwargs)
        if any(m.get("target") == "/tmp/harbor-mcode" for m in mounts_json or []):
            self._mounts_json = self._default_log_mounts() + list(mounts_json)
