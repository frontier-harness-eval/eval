"""Keep Pier's native evidence mounts alongside the Runta CA bind mount."""

from pier.environments.docker.docker import DockerEnvironment


class Environment(DockerEnvironment):
    def __init__(self, *args, mounts_json=None, **kwargs):
        # Pier treats a supplied mounts_json as a full replacement of its
        # defaults. When the runner adds the Runta CA bind mount, re-prepend
        # Pier's own log mounts so official verifier evidence is not dropped.
        super().__init__(*args, mounts_json=mounts_json, **kwargs)
        if mounts_json:
            self._mounts_json = self._default_log_mounts() + list(mounts_json)
