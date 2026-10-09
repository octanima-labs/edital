"""State-preserving reorder, retrying Save As, and recovery decisions."""

import asyncio

import pytest
from textual.widgets import Input, Static, Tabs

from edital import Edital
from edital.controls import HelpDialog
from edital.file_app import FileEditorApp, PathDialog, RecoveryDialog
from edital.tabs import DocumentTab


def test_keyboard_reordering_preserves_buffer_state_and_close_targets(tmp_path):
    async def exercise():
        editor = Edital(prompt=False)
        docs = editor.open(*(tmp_path / f"long-document-{i}.txt" for i in range(8)))
        active = docs[3]
        editor.session.active = active
        app = FileEditorApp(editor)
        async with app.run_test(size=(44, 20)) as pilot:
            await pilot.press("a", "b", "shift+left")
            area = app.areas[active.id]
            selection, history = area.selection, list(area.history.undo_stack)
            await pilot.press("ctrl+shift+pagedown")
            expected = [*docs[:3], docs[4], active, *docs[5:]]
            assert list(editor.files) == expected
            assert [t.id for t in app.query_one(Tabs).query(DocumentTab)] == [f"tab-{d.id}" for d in expected]
            assert editor.session.active is active and app.areas[active.id] is area
            assert area.selection == selection and area.history.undo_stack == history
            await pilot.press("ctrl+pagedown")
            assert editor.session.active is docs[5]
            await pilot.press("ctrl+pageup", "ctrl+shift+pageup")
            assert editor.files == docs and editor.session.active is active
            tab = app.query_one(f"#tab-{active.id}", DocumentTab)
            assert app.query_one("#tabs-scroll").region.overlaps(tab.region)
            await pilot.click(tab, offset=(tab.close_offset, 0))
            assert active not in editor.files and area not in app.areas.values()
            editor.session.active = editor.files[0]
            app.select_active()
            before = editor.files
            await pilot.press("ctrl+shift+pageup")
            assert editor.files == before
            editor.session.active = editor.files[-1]
            app.select_active()
            await pilot.press("ctrl+shift+pagedown")
            assert editor.files == before
            await pilot.press("f1", "ctrl+shift+pageup")
            assert editor.files == before
    asyncio.run(exercise())


@pytest.mark.parametrize("key", ["ctrl+s", "f2", "f3"])
def test_save_as_duplicate_retry_keeps_prompt_and_saves_once(tmp_path, key, monkeypatch):
    async def exercise():
        path = tmp_path / "existing"
        path.write_text("original")
        editor = Edital()
        existing, = editor.open(path)
        draft = editor.new()
        draft.text = "new text"
        save = editor.save
        successes = []

        def tracked(document, **kwargs):
            save(document, **kwargs)
            successes.append(document)

        monkeypatch.setattr(editor, "save", tracked)
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press(key)
            dialog = app.screen
            assert isinstance(dialog, PathDialog)
            entry = dialog.query_one(Input)
            entry.value = str(path)
            await pilot.press("enter")
            assert app.screen is dialog and entry.value == str(path)
            assert "already open" in str(dialog.query_one("#path-error", Static).content)
            assert draft.path is None and draft.baseline == "" and draft.text == "new text"
            assert path.read_text() == "original" and existing in editor.files
            await pilot.press("f1")
            assert isinstance(app.screen, HelpDialog)
            await pilot.press("escape")
            assert app.screen is dialog and dialog.focused is entry
            entry.value = str(tmp_path / "new")
            await pilot.press("enter")
            assert (tmp_path / "new").read_text() == "new text"
            assert successes.count(draft) == 1
            if key == "f2":
                assert draft not in editor.files and not editor.exited
            elif key == "f3":
                assert editor.exited
            else:
                assert draft in editor.files and not editor.exited
    asyncio.run(exercise())


@pytest.mark.parametrize("cancel", [False, True])
def test_save_as_filesystem_failure_retry_or_cancel(tmp_path, cancel):
    async def exercise():
        editor = Edital()
        draft = editor.new()
        draft.text = "kept"
        app = FileEditorApp(editor)
        async with app.run_test(size=(28, 20)) as pilot:
            await pilot.press("f2")
            dialog = app.screen
            entry = dialog.query_one(Input)
            entry.value = str(tmp_path / "missing" / "destination")
            await pilot.press("enter")
            assert app.screen is dialog and draft in editor.files and not editor.exited
            assert str(dialog.query_one("#path-error", Static).content)
            assert draft.path is None and draft.text == "kept" and draft.baseline == ""
            if cancel:
                await pilot.press("escape")
                assert draft in editor.files and draft.path is None
            else:
                entry.value = str(tmp_path / "saved")
                await pilot.press("enter")
                assert draft not in editor.files and (tmp_path / "saved").read_text() == "kept"
    asyncio.run(exercise())


def test_missing_recovery_prompt_and_choice(tmp_path):
    async def exercise():
        path = tmp_path / "deleted"
        path.write_text("base")
        prior = Edital()
        document, = prior.open(path)
        document.text = "cached"
        prior.exit()
        path.unlink()
        editor = Edital()
        restored, = editor.restore()
        app = FileEditorApp(editor)
        async with app.run_test(size=(32, 20)) as pilot:
            dialog = app.screen
            assert isinstance(dialog, RecoveryDialog)
            text = " ".join(str(s.content) for s in dialog.query(Static))
            assert "Destination is missing" in text and "empty named draft" in text
            assert "Restore cached version" in str(dialog.query_one("#recovered").label)
            assert "separate draft" in str(dialog.query_one("#draft").label)
            await pilot.press("f1", "escape")
            assert app.screen is dialog and restored.conflict
            await pilot.press("escape")
            assert restored.conflict and restored.text == "cached" and editor.cache
            editor.resolve_recovery(restored, "disk")
            assert restored.text == "" and restored.path == path
            assert not restored.conflict and not restored.autosave_eligible and not editor.cache
            assert not path.exists()
    asyncio.run(exercise())
