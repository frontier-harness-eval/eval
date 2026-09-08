"""Translate pip-install arguments for offline image preparation."""
import shlex


def uv_install_command(pip_args):
    """Add required boolean flags once, preserving other arguments and their order."""
    required = ("--system", "--break-system-packages")
    seen = set()
    args = []
    for arg in pip_args:
        if arg in required:
            if arg in seen:
                continue
            seen.add(arg)
        args.append(arg)
    return shlex.join(["uv", "pip", "install",
                       *(flag for flag in required if flag not in seen), *args])
