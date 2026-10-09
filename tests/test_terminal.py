"""Native POSIX terminal lifecycle smoke tests using actual escape sequences."""

import os
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Native Linux PTY verification")
@pytest.mark.parametrize("scenario", ["save", "failures", "controls", "dialogs", "recovery"])
def test_real_terminal(tmp_path, scenario):
    import fcntl
    import pty
    import select
    import struct
    import termios

    master, slave = pty.openpty()
    width = 32 if scenario in ("dialogs", "recovery") else 110
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, width, 0, 0))
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
    elif scenario == "controls":
        source += (
            "from edital.search import SearchPanel; "
            "replace_all=SearchPanel.replace_all; replacements=[]; "
            "SearchPanel.replace_all=lambda panel: (replace_all(panel),replacements.append("
            "(panel.area.text,panel.query_one('#find').value,panel.query_one('#replacement').value))); "
            "move=editor.session.move; moves=[]; "
            "editor.session.move=lambda doc,index: (moves.append((doc.path.name,index)),move(doc,index)); "
            "editor.run(); print('TERMINAL_DONE', editor.exited, moves, replacements)"
        )
        # F5, find term, replacement, Replace all, Escape, Undo, help, native reorder, finish.
        actions = [(b"\x1b[15~", 0.3), (b"second", 0.2), (b"\r", 0.2),
                   (b"\t", 0.2), (b"SECOND", 0.2),
                   (b"\t", 0.2), (b"\t", 0.2), (b"\t", 0.2), (b"\r", 0.4),
                   (b"\x1b", 0.3), (b"\x1a", 0.3), (b"\x1bOP", 0.3),
                   (b"\x1b[6~", 0.2), (b"\x1b", 0.3), (b"\x1b[5;6~", 0.3),
                   (b"\x1bOR", 0.4)]
    elif scenario == "dialogs":
        source += "editor.new().text='draft'; editor.run(); print('TERMINAL_DONE', editor.exited)"
        actions = [(b"\x13", 0.3), (str(tmp_path / "missing/file").encode(), 0.2),
                   (b"\r", 0.3), (b"\x1bOP", 0.3), (b"\x1b[6~", 0.2),
                   (b"\x1b", 0.3), (b"\x1b", 0.3), (b"\x1b", 0.4)]
    elif scenario == "recovery":
        source = (
            "from edital import Edital; from pathlib import Path; "
            f"path=Path({str(first)!r}); prior=Edital(); doc,=prior.open(path); "
            "doc.text='cached'; prior.exit(); path.unlink(); editor=Edital(); editor.restore(); "
            "editor.run(); print('TERMINAL_DONE',editor.exited)"
        )
        actions = [(b"\x1bOP", 0.3), (b"\x1b", 0.3), (b"\t\t", 0.3),
                   (b"\x1b", 0.3), (b"\x1b", 0.4)]
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
        elif scenario == "failures":
            assert b"cache failure" in transcript
            assert not (tmp_path / "missing/file").exists()
            assert list((tmp_path / "state/edital/recovery").glob("*.json"))
        elif scenario == "controls":
            assert b"('SECOND', 'second', 'SECOND')" in transcript, bytes(transcript)[-1000:]
            assert first.read_text() == "first" and second.read_text() == "second"
            assert b"('two', 0)" in transcript
            assert b"Keyboard cheatsheet" in transcript
        elif scenario == "dialogs":
            assert not (tmp_path / "missing/file").exists()
            assert b"Keyboard cheatsheet" in transcript
            assert list((tmp_path / "state/edital/recovery").glob("*.json"))
        elif scenario == "recovery":
            assert not first.exists()
            assert b"Destination is missing" in transcript
            assert list((tmp_path / "state/edital/recovery").glob("*.json"))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)
