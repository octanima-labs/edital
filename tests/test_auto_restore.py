"""Exercise launch-time recovery without bypassing the public run lifecycle."""

import pytest

from edital import Edital


@pytest.fixture
def launches(monkeypatch):
    from edital import editor
    from edital.file_app import FileEditorApp
    seen = []
    monkeypatch.setattr(editor.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(editor.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(FileEditorApp, "run", lambda app: seen.append(app.editor.files))
    return seen


def test_launch_restore_not_construction_and_independent_cache(tmp_path, launches):
    previous = Edital()
    draft = previous.new()
    draft.text = "snapshot"
    previous.exit()
    editor = Edital(auto_restore=True, cache=False)
    assert not editor.files
    explicit, = editor.open(tmp_path / "named")
    assert editor.files == (explicit,)
    editor.run()
    assert len(launches[-1]) == 2
    assert launches[-1][1].text == "snapshot"
    assert editor.conf.get("cache") is False
    assert len(editor.cache) == 1


def test_explicit_restore_and_repeated_run_are_idempotent(launches):
    previous = Edital()
    draft = previous.new()
    draft.text = "snapshot"
    previous.exit()
    editor = Edital(auto_restore=True)
    restored, = editor.restore()
    restored.text = "new unsaved edits"
    editor.run(create_draft=True)
    editor.run(create_draft=True)
    assert launches == [(restored,), (restored,)]
    assert restored.text == "new unsaved edits" and len(editor.cache) == 1


def test_api_false_override_and_default_empty_workspace(user_storage, launches):
    previous = Edital()
    previous.new().text = "snapshot"
    previous.exit()
    user_storage[0].write_text("auto_restore: true\n")
    editor = Edital(auto_restore=False)
    editor.run()
    assert launches[-1] == () and len(editor.cache) == 1
    editor.run(create_draft=True)
    assert len(launches[-1]) == 1 and launches[-1][0].text == ""
    assert user_storage[0].read_text() == "auto_restore: true\n"


def test_launch_conflict_keeps_disk_safe(tmp_path, launches):
    path = tmp_path / "file"
    path.write_text("baseline")
    previous = Edital()
    document, = previous.open(path)
    document.text = "snapshot"
    previous.exit()
    path.write_text("changed externally")
    editor = Edital(auto_restore=True, auto_save=10)
    opened, = editor.open(path)
    editor.run()
    assert launches[-1] == (opened,)
    assert opened.text == "snapshot" and opened.conflict
    assert editor.autosave() == ()
    assert path.read_text() == "changed externally" and len(editor.cache) == 1


def test_noninteractive_launch_does_not_restore(monkeypatch):
    from edital import editor as facade
    previous = Edital()
    previous.new().text = "snapshot"
    previous.exit()
    editor = Edital(auto_restore=True)
    monkeypatch.setattr(facade.sys.stdin, "isatty", lambda: False)
    with pytest.raises(RuntimeError, match="interactive"):
        editor.run(create_draft=True)
    assert not editor.files and len(editor.cache) == 1
