"""Native POSIX terminal lifecycle smoke tests using actual escape sequences."""

import os
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Native Linux PTY verification")
@pytest.mark.parametrize("scenario", ["save", "failures"])
def test_real_terminal(tmp_path, scenario):
    import fcntl
    import pty
    import select
    import struct
    import termios

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
    before = termios.tcgetattr(slave)
    environment = os.environ.copy()
    environment.update(TERM="xterm-256color", XDG_CONFIG_HOME=str(tmp_path / "config"),
                       XDG_STATE_HOME=str(tmp_path / "state"))
    first, second = tmp_path / "one", tmp_path / "two"
    first.write_text("first")
    second.write_text("second")
    source = (
        "from edital import Edital; "
        "from pathlib import Path; "
        f"editor=Edital(); editor.open({str(first)!r}, {str(second)!r}); "
    )
    if scenario == "failures":
        source += (
            f"editor.session.active.path=Path({str(tmp_path / 'missing/file')!r}); "
            "original=editor._recovery.snapshot; attempts=[]; "
            "editor._recovery.snapshot=lambda doc: original(doc) if attempts else "
            "(attempts.append(True), (_ for _ in ()).throw(OSError('cache failure'))); "
            "editor.run(); print('TERMINAL_DONE', editor.exited)"
        )
        actions = [(b"x", 0.2), (b"\x1bOR", 0.4), (b"\x1b", 0.4), (b"\x1b", 0.4)]
    else:
        source += "editor.run(); print('TERMINAL_DONE', editor.exited)"
        # Ctrl+PageUp selects first; F2 saves/closes it; F3 saves remaining and exits.
        actions = [(b"\x1b[5;5~", 0.2), (b"x", 0.2), (b"\x1bOQ", 0.3), (b"\x1bOR", 0.3)]
    process = subprocess.Popen([sys.executable, "-c", source], stdin=slave, stdout=slave,
                               stderr=slave, env=environment)
    transcript = bytearray()

    def drain(duration):
        until = time.monotonic() + duration
        while time.monotonic() < until:
            if select.select([master], [], [], 0.02)[0]:
                transcript.extend(os.read(master, 65536))

    try:
        drain(1)
        for keys, duration in actions:
            if keys is not None:
                os.write(master, keys)
            drain(duration)
        deadline = time.monotonic() + 8
        while process.poll() is None and time.monotonic() < deadline:
            drain(0.1)
        assert process.poll() == 0, bytes(transcript)[-3000:]
        drain(0.1)
        assert b"TERMINAL_DONE True" in transcript
        assert termios.tcgetattr(slave) == before
        assert b"\x1b[?1049l" in transcript
        if scenario == "save":
            assert first.read_text() == "xfirst" and second.read_text() == "second"
        else:
            assert b"cache failure" in transcript
            assert not (tmp_path / "missing/file").exists()
            assert list((tmp_path / "state/edital/recovery").glob("*.json"))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)
