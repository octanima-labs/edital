"""Exercise standalone document actions through actual Textual key dispatch."""

import asyncio

from textual.widgets import Input, Static, Tabs

from edital import Edital
from edital.file_app import FileEditorApp, PathDialog, RecoveryDialog


def test_tabs_retain_state_and_empty_workspace(tmp_path):
    async def exercise():
        editor = Edital(prompt=False)
        first, second = editor.new(), editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("a", "b", "shift+left")
            area = app.areas[second.id]
            selection = area.selection
            history = list(area.history.undo_stack)
            await pilot.press("ctrl+pageup")
            assert editor.session.active is first
            await pilot.press("x", "ctrl+pagedown")
            assert editor.session.active is second
            assert area.text == "ab" and area.selection == selection
            assert area.history.undo_stack == history
            await pilot.press("ctrl+w", "ctrl+n")
            assert editor.files[-1].draft_name == "draft (2)"
            await pilot.press("ctrl+w", "ctrl+w")
            assert not editor.files and not editor.exited
            assert app.query_one("#empty").display
            await pilot.press("escape", "escape")
            assert app.is_running and not editor.exited
            await pilot.press("ctrl+q")
        assert editor.exited
    asyncio.run(exercise())


def test_save_as_cancel_save_close_and_find(tmp_path):
    async def exercise():
        editor = Edital()
        draft = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("h", "i", "f2")
            assert isinstance(app.screen, PathDialog)
            await pilot.press("escape")
            assert draft in editor.files and draft.text == "hi"
            await pilot.press("f4")
            assert app.query_one("#find").display
            app.query_one("#find", Input).value = "hi"
            await pilot.press("enter", "escape")
            assert not editor.exited and not app.query_one("#find").display
            await pilot.press("f2")
            app.screen.query_one(Input).value = str(tmp_path / "saved")
            await pilot.press("enter")
            assert not editor.files and not editor.exited
            assert (tmp_path / "saved").read_text() == "hi"
            await pilot.press("ctrl+q")
    asyncio.run(exercise())


def test_periodic_autosave_and_reschedule(tmp_path):
    async def exercise():
        path = tmp_path / "existing"
        path.write_text("")
        editor = Edital(auto_save=40)
        existing, draft = editor.open(path, tmp_path / "draft")
        editor.session.active = existing
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            for key in "continuous":
                await pilot.press(key)
                await asyncio.sleep(0.02)
            await pilot.pause(0.1)
            assert path.read_text() == "continuous"
            assert not existing.modified
            editor.conf.set("auto_save", 0)
            assert app._timer is None
            await pilot.press("x")
            await pilot.pause(0.1)
            assert path.read_text() == "continuous"
            editor.conf.set("auto_save", 30)
            await pilot.pause(0.1)
            assert path.read_text() == "continuousx"
            await pilot.press("ctrl+pagedown", "d")
            await pilot.pause(0.1)
            assert draft.modified and not draft.path.exists()
            await pilot.press("ctrl+q")
        assert len(editor.cache) == 1
    asyncio.run(exercise())


def test_discard_refusal_and_no_prompt():
    async def exercise():
        editor = Edital(cache=False)
        draft = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("x", "ctrl+w")
            await pilot.click("#keep")
            assert draft in editor.files
            await pilot.press("ctrl+q", "escape")
            assert not editor.exited
            editor.conf.set("prompt", False)
            await pilot.press("ctrl+q")
        assert editor.exited and not editor.cache
    asyncio.run(exercise())


def test_failed_save_all_and_cache_exit(tmp_path, monkeypatch):
    async def exercise():
        editor = Edital()
        first, second = editor.open(tmp_path / "one", tmp_path / "missing/two")
        first.text, second.text = "one", "two"
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("f3")
            assert editor.files and not editor.exited
            assert first.path.read_text() == "one" and second.modified
            assert str(app.query_one("#diagnostic", Static).content)
            snapshot = editor._recovery.snapshot

            def fail(document):
                raise OSError("cache unavailable")

            monkeypatch.setattr(editor._recovery, "snapshot", fail)
            await pilot.press("f5")
            field = app.query_one("#find", Input)
            field.value = "two"
            await pilot.press("ctrl+q")
            assert not editor.exited and editor.files
            assert app.focused is field and field.value == "two"
            monkeypatch.setattr(editor._recovery, "snapshot", snapshot)
            await pilot.press("ctrl+q")
        assert len(editor.cache) == 1
    asyncio.run(exercise())


def test_recovery_with_running_timer(tmp_path):
    async def exercise():
        path = tmp_path / "document"
        path.write_text("base")
        previous = Edital()
        document, = previous.open(path)
        document.text = "recovery"
        previous.exit()
        path.write_text("external")
        editor = Edital(auto_save=30)
        recovered, = editor.restore()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.pause(0.1)
            assert isinstance(app.screen, RecoveryDialog)
            assert path.read_text() == "external"
            await pilot.click("#recovered")
            await pilot.pause(0.15)
            assert not recovered.conflict and path.read_text() == "recovery"
            await pilot.press("ctrl+q")
    asyncio.run(exercise())


def test_open_labels_and_save_all_cancel(tmp_path):
    async def exercise():
        left, right = tmp_path / "left", tmp_path / "right"
        left.mkdir()
        right.mkdir()
        editor = Edital()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            for path in (left / "[notes].txt", right / "[notes].txt"):
                await pilot.press("ctrl+o")
                app.screen.query_one(Input).value = str(path)
                await pilot.press("enter")
            assert len(editor.files) == 2
            for document in editor.files:
                tab = app.query_one(Tabs).get_tab(f"tab-{document.id}")
                assert tab.label.plain == f"{document.path}  ⨯"
            await pilot.press("ctrl+n", "x", "f3")
            assert isinstance(app.screen, PathDialog)
            await pilot.press("escape")
            assert not editor.exited and len(editor.files) == 3
            await pilot.press("ctrl+q")
    asyncio.run(exercise())
