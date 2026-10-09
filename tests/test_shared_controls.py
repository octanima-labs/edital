"""Cross-mode keyboard behavior, search edits, undo, and nested help."""

import asyncio

import pytest
from rich.text import Text
from textual.document._document import Selection
from textual.widgets import Input, Static, TextArea

from edital import Edital, EditResult
from edital.app import EditorApp
from edital.controls import HelpDialog
from edital.file_app import FileEditorApp, PathDialog
from edital.search import SearchPanel


@pytest.mark.parametrize("mode", ["embedded", "standalone"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_shared_search_replacement_history_and_fidelity(mode, newline, user_storage):
    async def exercise():
        text = f"a.a{newline}a.a"
        editor = None
        if mode == "embedded":
            app = EditorApp(text)
        else:
            editor = Edital()
            document = editor.new()
            document.text, document.newline = text, newline
            app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            area = app.query_one(TextArea)
            await pilot.press("x", "f5")
            panel = app.query_one(SearchPanel)
            app.query_one("#find", Input).value = "a.a"
            app.query_one("#replacement", Input).value = "a.aa.a"
            await pilot.press("enter")
            assert area.selected_text == "a.a"
            panel.find_next()
            assert area.selection.start == (1, 0)
            panel.find_next()
            assert area.selection.start == (0, 1)  # Wraps, punctuation is literal.
            panel.replace_all()
            await pilot.pause()
            assert area.text == "xa.aa.a\na.aa.a"
            assert "2 replacements" in str(panel.query_one("#search-result", Static).content)
            await pilot.press("escape", "ctrl+z")
            assert area.text == "xa.a\na.a"
            await pilot.press("ctrl+z")
            assert area.text == "a.a\na.a"  # Earlier typing remains undoable.
            await pilot.press("ctrl+y", "ctrl+y")
            assert area.text == "xa.aa.a\na.aa.a"
            if mode == "embedded":
                assert app.candidate == f"xa.aa.a{newline}a.aa.a"
                assert not user_storage[0].exists()
            else:
                assert document.text == f"xa.aa.a{newline}a.aa.a"
                assert document.modified
    asyncio.run(exercise())


def test_safe_replace_empty_inputs_stale_selection_and_terms():
    async def exercise():
        app = EditorApp("a A a")
        async with app.run_test() as pilot:
            area = app.query_one(TextArea)
            await pilot.press("f5")
            panel = app.query_one(SearchPanel)
            panel.replace_all()
            assert area.text == "a A a"
            assert "nonempty" in str(panel.query_one("#search-result", Static).content)
            app.query_one("#find", Input).value = "a"
            panel.replace_one()  # Find first, rather than replace with no match.
            assert area.text == "a A a" and area.selected_text == "a"
            area.selection = Selection((0, 2), (0, 3))
            panel.replace_one()
            assert area.text == "a A a" and area.selected_text == "a"
            panel.replace_one()  # Empty replacement deletes only the matched lowercase a.
            assert area.text == "a A "
            panel.replace_all()
            assert area.text == " A "
            app.query_one("#find", Input).value = "missing"
            panel.find_next()
            assert "not found" in str(panel.query_one("#search-result", Static).content)
            await pilot.press("f4")
            assert app.query_one("#find", Input).value == "missing"
            assert not app.query_one("#replacement").display
            await pilot.press("f5")
            assert app.query_one("#replacement").display
    asyncio.run(exercise())


def test_embedded_reserved_keys_acceptance_validation_and_selection():
    async def exercise():
        app = EditorApp("seed", validator=lambda text: "Rejected" if text != "good" else None)
        async with app.run_test() as pilot:
            area = app.query_one(TextArea)
            area.move_cursor((0, 4))
            await pilot.press("ctrl+w", "ctrl+s", "ctrl+n", "ctrl+o", "ctrl+a")
            assert area.text == "seed" and area.cursor_location == (0, 0)
            await pilot.press("f7")
            assert area.selected_text == "seed"
            await pilot.press("f3")
            assert "Rejected" in str(app.query_one("#diagnostic", Static).content)
            assert area.selected_text == "seed" and app.is_running
            await pilot.press("g", "o", "o", "d", "f3")
        assert app.return_value == EditResult("accepted", "good")
    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["standalone", "embedded"])
def test_help_effective_bindings_and_search_focus(mode):
    async def exercise():
        if mode == "embedded":
            app = EditorApp("seed")
        else:
            editor = Edital()
            editor.new().text = "seed"
            app = FileEditorApp(editor)
        async with app.run_test(size=(30, 16)) as pilot:
            await pilot.press("f5")
            term = app.query_one("#find", Input)
            term.value = "seed"
            area = app.query_one(TextArea)
            selection = area.selection
            await pilot.press("f1")
            assert isinstance(app.screen, HelpDialog)
            help_text = app.screen.text
            headings = list(app.screen.query(".help-heading"))
            assert len(headings) >= 6
            assert all(heading.styles.text_style.bold for heading in headings)
            bodies = list(app.screen.query(".help-body"))
            assert bodies and all(isinstance(body.content, Text) for body in bodies)
            assert any(span.style == "bold yellow" for body in bodies for span in body.content.spans)
            assert "f6: Select line" in help_text and "f7: Select all" in help_text
            assert "ctrl+w: Close tab" in help_text
            assert "ctrl+w: Delete" not in help_text
            assert "ctrl+q: Quit" in help_text and "ctrl+p:" in help_text
            if mode == "embedded":
                assert "unavailable in embedded" in help_text
            await pilot.press("f2", "f3", "f4", "f5", "ctrl+w", "ctrl+shift+pageup", "ctrl+q", "ctrl+p")
            assert isinstance(app.screen, HelpDialog) and area.text == "seed"
            await pilot.press("pagedown", "escape")
            assert app.focused is term and term.value == "seed"
            assert area.selection == selection
            await pilot.press("escape")
            assert app.focused is area and app.is_running
    asyncio.run(exercise())


def test_nested_help_keeps_path_and_discard_prompts():
    async def exercise():
        editor = Edital()
        document = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("x", "ctrl+s")
            dialog = app.screen
            assert isinstance(dialog, PathDialog)
            path = dialog.query_one(Input)
            path.value = "chosen-path"
            await pilot.press("f1", "f2", "f3", "escape")
            assert app.screen is dialog and dialog.focused is path
            assert path.value == "chosen-path" and document.path is None
            await pilot.press("escape", "ctrl+w")
            discard = app.screen
            await pilot.press("f1", "f1")
            assert app.screen is discard and document in editor.files
    asyncio.run(exercise())


def test_replace_only_active_document_and_invalidates_match_after_switch():
    async def exercise():
        editor = Edital()
        first, second = editor.new(), editor.new()
        first.text = second.text = "a a"
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("f5")
            panel = app.query_one(SearchPanel)
            app.query_one("#find", Input).value = "a"
            app.query_one("#replacement", Input).value = "b"
            panel.find_next()
            await pilot.press("ctrl+pageup")
            assert panel.match is None
            panel.replace_one()
            assert first.text == "a a"
            panel.replace_all()
            await pilot.pause()
            assert first.text == "b b" and second.text == "a a"
    asyncio.run(exercise())
