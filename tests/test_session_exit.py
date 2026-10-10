"""Verify deliberate session termination and interaction-only Escape."""

import asyncio

import pytest
from textual.widgets import Input, TextArea

from edital import Edital, EditResult
from edital.app import DiscardDialog, EditorApp
from edital.controls import HelpDialog
from edital.document_picker import DocumentPicker
from edital.file_app import FileEditorApp, PathDialog, RecoveryDialog
from edital.search import SearchPanel


@pytest.mark.parametrize("mode", ["standalone", "embedded"])
@pytest.mark.parametrize("changed", [False, True])
def test_repeated_escape_only_dismisses_interactions(mode, changed):
    async def exercise():
        editor = Edital()
        if mode == "standalone":
            editor.new().text = "seed"
            app = FileEditorApp(editor)
        else:
            app = EditorApp("seed")
        async with app.run_test(size=(32, 20)) as pilot:
            if changed:
                await pilot.press("x", "shift+right")
            area = app.query_one(TextArea)
            text, selection, history = area.text, area.selection, list(area.history.undo_stack)
            await pilot.press("escape", "escape", "f5")
            field = app.query_one("#find", Input)
            field.value = "seed"
            await pilot.press("f1", "escape")
            assert app.query_one(SearchPanel).display and app.focused is field
            await pilot.press("escape", "escape", "escape")
            assert len(app.screen_stack) == 1 and app.is_running and app.return_value is None
            assert not app.query_one(SearchPanel).display and app.focused is area
            assert area.text == text and area.selection == selection and area.history.undo_stack == history
            if mode == "standalone":
                assert len(editor.files) == 1 and not editor.exited and not editor.cache
    asyncio.run(exercise())


def test_ctrl_q_from_search_preserves_unsaved_documents_without_saving(tmp_path):
    async def exercise():
        path = tmp_path / "saved"
        path.write_text("baseline")
        editor = Edital()
        saved, = editor.open(path)
        draft = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            app.areas[saved.id].insert("x", (0, 0))
            await pilot.press(*"draft", "f5")
            await pilot.press("ctrl+q")
        assert editor.exited and not editor.files and len(editor.cache) == 2
        assert path.read_text() == "baseline" and draft.path is None
        restored = Edital().restore()
        assert {document.text for document in restored} == {"xbaseline", "draft"}
    asyncio.run(exercise())


@pytest.mark.parametrize("prompt", [False, True])
@pytest.mark.parametrize("conflict", [False, True])
def test_standalone_ctrl_q_uses_discard_rules_and_restores_search(prompt, conflict):
    async def exercise():
        editor = Edital(cache=False, prompt=prompt)
        document = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("x", "shift+left", "f5")
            document.conflict = conflict
            area = app.areas[document.id]
            selection, history = area.selection, list(area.history.undo_stack)
            field = app.query_one("#find", Input)
            field.value = "x"
            app.query_one("#replacement", Input).value = "y"
            await pilot.press("ctrl+q")
            if prompt:
                dialog = app.screen
                assert isinstance(dialog, DiscardDialog)
                await pilot.press("ctrl+q", "f1", "ctrl+q", "escape")
                assert app.screen is dialog and editor.files == (document,)
                await pilot.click("#keep")
                assert app.focused is field and app.query_one(SearchPanel).display
                await pilot.press("ctrl+q", "escape")
                assert app.focused is field and app.query_one(SearchPanel).display
                assert field.value == "x" and app.query_one("#replacement", Input).value == "y"
                assert area.text == "x" and area.selection == selection and area.history.undo_stack == history
                assert editor.files == (document,) and not editor.exited
                await pilot.press("ctrl+q")
                await pilot.click("#discard")
        assert editor.exited and not editor.files and not editor.cache
    asyncio.run(exercise())


@pytest.mark.parametrize("modal", ["path", "recovery", "picker"])
def test_standalone_modal_blocks_keyboard_and_direct_quit(modal):
    async def exercise():
        editor = Edital(cache=False)
        document = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("x")
            if modal == "path":
                await pilot.press("ctrl+o")
                assert isinstance(app.screen, PathDialog)
            elif modal == "recovery":
                app.push_screen(RecoveryDialog(document))
                await pilot.pause()
            else:
                await pilot.press("f8")
                assert isinstance(app.screen, DocumentPicker)
            screen = app.screen
            await pilot.press("ctrl+q")
            await app.action_quit()
            await pilot.pause()
            assert app.screen is screen and editor.files == (document,)
            assert not editor.exited and not editor.cache
            await pilot.press("escape", "escape")
            assert app.is_running and len(app.screen_stack) == 1
    asyncio.run(exercise())


def test_embedded_ctrl_q_from_search_preserves_context_on_refusal(user_storage):
    async def exercise():
        app = EditorApp("seed", validator=lambda _: pytest.fail("Cancellation must not validate"))
        async with app.run_test() as pilot:
            await pilot.press("x", "shift+right", "f5")
            area = app.query_one(TextArea)
            selection, history = area.selection, list(area.history.undo_stack)
            field = app.query_one("#find", Input)
            field.value = "seed"
            app.query_one("#replacement", Input).value = "other"
            for answer in ("keep", "escape"):
                await pilot.press("ctrl+q")
                dialog = app.screen
                assert isinstance(dialog, DiscardDialog)
                await pilot.press("ctrl+q", "f1", "ctrl+q")
                assert isinstance(app.screen, HelpDialog)
                await app.action_quit()
                await pilot.press("escape")
                assert app.screen is dialog
                await app.action_quit()
                if answer == "keep":
                    await pilot.click("#keep")
                else:
                    await pilot.press("escape")
                assert app.is_running and app.return_value is None
                assert app.focused is field and app.query_one(SearchPanel).display
                assert field.value == "seed" and app.query_one("#replacement", Input).value == "other"
                assert area.text == "xseed" and area.selection == selection and area.history.undo_stack == history
            await pilot.press("ctrl+q")
            await pilot.click("#discard")
        assert app.return_value == EditResult("cancelled")
        assert not user_storage[0].exists() and not user_storage[1].exists()
    asyncio.run(exercise())


def test_embedded_unchanged_quit_from_search_returns_cancelled(user_storage):
    async def exercise():
        app = EditorApp("seed", validator=lambda _: pytest.fail("Cancellation must not validate"))
        async with app.run_test() as pilot:
            await pilot.press("f4", "ctrl+q")
        assert app.return_value == EditResult("cancelled")
        assert not user_storage[0].exists() and not user_storage[1].exists()
    asyncio.run(exercise())
