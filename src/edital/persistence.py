"""UTF-8 text persistence without newline translation or partial replacement."""

import os
import stat
import tempfile
from pathlib import Path


def read_text(path: Path) -> str:
    """Read exact UTF-8 text, including its original newline convention."""
    with path.open(encoding="utf-8", newline="") as stream:
        return stream.read()


def write_text(path: Path, text: str) -> None:
    """Stage and replace text, following symlinks and retaining existing permissions.

    Parent directories must already exist. Errors leave the prior file intact.
    """
    target = path.resolve()
    mode = None
    if target.exists():
        mode = stat.S_IMODE(target.stat().st_mode)
        if mode & 0o222 == 0:
            raise PermissionError(f"Destination is read-only: {target}")
    fd, name = tempfile.mkstemp(prefix=".edital-", dir=target.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            staged.chmod(mode)
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)
