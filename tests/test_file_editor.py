"""Public session lifecycle and recovery preservation at filesystem boundaries."""

import pytest

from edital import ConfirmationRequired, Edital


def test_explicit_cache_and_fresh_sessions(tmp_path):
    editor = Edital(cache=False)
    draft = editor.new()
    draft.text = "α\r\nunsaved"
    draft.newline = "\r\n"
    with pytest.raises(ConfirmationRequired):
        editor.close(draft)
    editor.close(draft, cache=True)
    assert not editor.files and not editor.exited
    assert editor.cache[0].size == len(draft.text.encode("utf-8"))
    fresh = Edital(cache=False)
    assert not fresh.files
    assert len(fresh.list(cache=True)) == 1
    restored, = fresh.restore()
    assert restored.text == draft.text
    assert restored.newline == "\r\n"
    assert len(fresh.cache) == 1
    assert fresh.restore() == (restored,)
    fresh.save(restored, path=tmp_path / "saved")
    assert not fresh.cache
    assert (tmp_path / "saved").read_bytes() == draft.text.encode("utf-8")


def test_exit_failure_keeps_documents(tmp_path, monkeypatch):
    editor = Edital()
    first, second = editor.new(), editor.new()
    first.text, second.text = "one", "two"
    snapshot = editor._recovery.snapshot

    def fail(document):
        if document is second:
            raise OSError("storage failure")
        snapshot(document)

    monkeypatch.setattr(editor._recovery, "snapshot", fail)
    with pytest.raises(OSError, match="storage failure"):
        editor.exit()
    assert editor.files == (first, second) and not editor.exited
    monkeypatch.setattr(editor._recovery, "snapshot", snapshot)
    editor.exit()
    assert editor.exited and not editor.files and len(editor.cache) == 2


@pytest.mark.parametrize("choice", ["recovered", "disk", "draft"])
def test_conflict_choices(tmp_path, choice):
    path = tmp_path / "document"
    path.write_text("baseline")
    previous = Edital()
    document, = previous.open(path)
    document.text = "recovered"
    previous.exit()
    path.write_text("external change")
    editor = Edital(auto_save=10)
    editor.open(path)
    recovered, = editor.restore()
    assert len(editor.files) == 1 and recovered.conflict
    assert not editor.autosave()
    assert path.read_text() == "external change"
    with pytest.raises(ValueError, match="conflict"):
        editor.save(recovered)
    editor.resolve_recovery(recovered, choice)
    assert not recovered.conflict
    assert path.read_text() == "external change"
    if choice == "recovered":
        assert recovered.modified and len(editor.cache) == 1
        editor.autosave()
        assert path.read_text() == "recovered" and not editor.cache
    elif choice == "disk":
        assert recovered.text == "external change" and not recovered.modified
        assert not editor.cache
    else:
        assert recovered.path is None and not recovered.autosave_eligible
        assert len(editor.files) == 2 and len(editor.cache) == 1
        editor.autosave()
        assert path.read_text() == "external change"


def test_matching_path_merge_and_purge(tmp_path):
    path = tmp_path / "file"
    path.write_text("base")
    previous = Edital()
    document, = previous.open(path)
    document.text = "unsaved"
    previous.exit()
    editor = Edital()
    original, = editor.open(path)
    restored, = editor.restore()
    assert restored is original and len(editor.files) == 1
    assert restored.modified and not restored.conflict
    editor.clear_cache()
    assert not editor.cache
    assert restored.text == "unsaved" and path.read_text() == "base"


def test_discard_recache_and_unrelated_entries(tmp_path):
    first, second = Edital(), Edital()
    draft1, draft2 = first.new(), second.new()
    draft1.text, draft2.text = "one", "two"
    first.exit()
    second.exit()
    assert len(first.cache) == 2
    editor = Edital(prompt=False)
    documents = editor.restore()
    editor.close(documents[0])
    assert len(editor.cache) == 1
    documents[1].text = "new revision"
    editor.exit()
    assert len(editor.cache) == 1 and editor.cache[0].text == "new revision"


def test_autosave_eligibility_errors_and_revision(tmp_path, monkeypatch):
    path = tmp_path / "existing"
    path.write_text("base")
    editor = Edital(auto_save=10)
    existing, named = editor.open(path, tmp_path / "new")
    draft = editor.new()
    existing.text, named.text, draft.text = "changed", "named", "draft"
    assert editor.autosave() == ()
    assert path.read_text() == "changed" and not named.path.exists()
    editor.save(named)
    named.text = "eligible now"
    editor.autosave()
    assert named.path.read_text() == "eligible now"
    from edital import documents
    write = documents.write_text

    def edit_during_write(destination, text):
        write(destination, text)
        existing.text = "later revision"

    existing.text = "captured revision"
    monkeypatch.setattr(documents, "write_text", edit_during_write)
    editor.autosave()
    assert existing.baseline == "captured revision" and existing.modified

    def fail(destination, text):
        raise OSError("cannot write")

    monkeypatch.setattr(documents, "write_text", fail)
    errors = editor.autosave()
    assert errors[0][0] is existing and existing.modified
    editor.conf.set("auto_save", 0)
    assert editor.autosave() == ()


def test_no_cache_exit_requires_confirmation():
    editor = Edital(cache=False)
    draft = editor.new()
    draft.text = "unsaved"
    with pytest.raises(ConfirmationRequired):
        editor.exit()
    assert editor.files and not editor.exited
    editor.conf.set("prompt", False)
    editor.exit()
    assert not editor.files and editor.exited and not editor.cache


def test_embedded_no_storage_side_effects(user_storage, monkeypatch):
    import edital
    from edital import EditResult, edit_text
    from edital.app import EditorApp
    monkeypatch.setattr(edital.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(edital.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(EditorApp, "run", lambda app: EditResult("cancelled"))
    assert edit_text("text") == EditResult("cancelled")
    assert not user_storage[0].exists() and not user_storage[1].exists()


def test_recovered_draft_label_and_disk_newlines(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"base\r\n")
    prior = Edital()
    document, = prior.open(path)
    document.text = "recovered\r\n"
    prior.exit()
    path.write_bytes(b"external\n")
    editor = Edital()
    draft = editor.new()
    editor.open(path)
    recovered, = editor.restore()
    editor.resolve_recovery(recovered, "draft")
    assert recovered.draft_name != draft.draft_name
    assert recovered.draft_name == "draft (1)"
    # Disk choice must adopt the disk's convention, not stale snapshot CRLF.
    other = Edital()
    restored, = other.restore()
    other.resolve_recovery(restored, "disk")
    assert restored.newline == "\n" and restored.text == "external\n"


@pytest.mark.parametrize("choice", ["disk", "recovered"])
def test_rejected_duplicate_resolution_preserves_snapshot_and_state(tmp_path, choice):
    path = tmp_path / "file"
    path.write_text("base")
    prior = Edital()
    document, = prior.open(path)
    document.text = "cached"
    prior.exit()
    editor = Edital()
    other, = editor.open(path)
    other.text = "independent unsaved edit"
    restored, = editor.restore()
    state, snapshots = vars(restored).copy(), editor.cache
    with pytest.raises(ValueError, match="another unsaved"):
        editor.resolve_recovery(restored, choice)
    assert vars(restored) == state and editor.cache == snapshots
    assert other.text == "independent unsaved edit" and restored.conflict
    editor.resolve_recovery(restored, "draft")
    assert restored.path is None and restored.recovery_id == state["recovery_id"]
    assert other in editor.files and other.text == "independent unsaved edit"
    assert restored.text == "cached" and editor.cache == snapshots
    assert path.read_text() == "base"


def test_missing_named_draft_is_not_a_recovery_conflict(tmp_path):
    path = tmp_path / "never-created"
    prior = Edital()
    draft, = prior.open(path)
    draft.text = "cached draft"
    prior.exit()
    editor = Edital()
    restored, = editor.restore()
    assert not restored.conflict and restored.text == "cached draft"
    assert not restored.autosave_eligible and not path.exists()


def test_separate_draft_read_failure_is_nondestructive(tmp_path, monkeypatch):
    path = tmp_path / "file"
    path.write_text("base")
    prior = Edital()
    document, = prior.open(path)
    document.text = "cached"
    prior.exit()
    path.write_text("changed")
    editor = Edital()
    restored, = editor.restore()
    state, snapshots = vars(restored).copy(), editor.cache

    def fail(path):
        raise OSError("cannot read destination")

    monkeypatch.setattr("edital.editor.read_text", fail)
    with pytest.raises(OSError, match="cannot read"):
        editor.resolve_recovery(restored, "draft")
    assert vars(restored) == state and editor.cache == snapshots
