"""Filesystem-backed document contracts, without launching a terminal."""

import os

import pytest

from edital.documents import EditalSession


def test_drafts_identity_and_baselines(tmp_path):
    session = EditalSession()
    path = tmp_path / "named.txt"
    named, = session.open(path)
    first, second = session.new(), session.new()
    assert len({named.id, first.id, second.id}) == 3
    assert not path.exists()
    assert session.open(path)[0] is named
    assert session.active is named
    assert not named.autosave_eligible
    first.text = "hello"
    assert first.modified
    first.text = ""
    assert not first.modified
    assert first.unsaved
    with pytest.raises(ValueError, match="destination"):
        session.save(first)
    session.save(first, path=tmp_path / "saved.txt")
    assert first.autosave_eligible and not first.modified
    assert isinstance(session.files, tuple)


@pytest.mark.parametrize("text", ["", "α  \n\n", "hello", "a\r\nb\r\n", "# x\r\nx: 1"])
def test_text_fidelity(tmp_path, text):
    path = tmp_path / "document"
    path.write_bytes(text.encode("utf-8"))
    session = EditalSession()
    document, = session.open(path)
    assert document.text == text
    session.save(document)
    assert path.read_bytes() == text.encode("utf-8")


def test_partial_save_all_and_failure(tmp_path):
    session = EditalSession()
    first, second = session.open(tmp_path / "first", tmp_path / "missing" / "second")
    first.text = "saved"
    second.text = "still here"
    with pytest.raises(OSError):
        session.save_all()
    assert first.path.read_text() == "saved"
    assert not first.modified
    assert second.modified and second in session.files
    assert not second.autosave_eligible


def test_symlink_and_permissions(tmp_path):
    path = tmp_path / "target"
    path.write_text("old")
    link = tmp_path / "link"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("Symlinks unavailable for this user")
    session = EditalSession()
    document, = session.open(link)
    assert session.open(path)[0] is document
    if os.name != "nt":
        path.chmod(0o640)
    document.text = "new"
    session.save(document)
    assert link.is_symlink() and path.read_text() == "new"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o640


def test_unsupported_and_duplicate_save_destination(tmp_path):
    path = tmp_path / "mixed"
    path.write_bytes(b"a\r\nb\n")
    session = EditalSession()
    with pytest.raises(ValueError, match="line endings"):
        session.open(path)
    one, two = session.open(tmp_path / "one", tmp_path / "two")
    with pytest.raises(ValueError, match="already open"):
        session.save(one, path=two.path)
