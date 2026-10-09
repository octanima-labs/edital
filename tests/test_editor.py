"""Exercise the session contract through actual Textual key dispatch."""

import asyncio
import subprocess
import sys

import pytest
from textual.widgets import Input, Static, TextArea

from edital import EditResult, edit_text
from edital.app import DiscardDialog, EditorApp


@pytest.mark.parametrize("text", ["", "hello", "# header\nx: 1\n", "# header\r\nx: 1", "a\r\n\r\n", "  α\n\n"])
def test_unchanged_acceptance_preserves_exact_text(text):
    async def exercise():
        app = EditorApp(text)
        async with app.run_test() as pilot:
            await pilot.press("f2")
        assert app.return_value == EditResult("accepted", text)
    asyncio.run(exercise())


def test_validation_preserves_cursor_history_and_allows_correction():
    async def exercise():
        app = EditorApp("", validator=lambda text: "Use good" if text != "good" else None)
        async with app.run_test() as pilot:
            await pilot.press("b", "a", "d")
            area = app.query_one(TextArea)
            cursor = area.cursor_location
            history = list(area.history.undo_stack)
            await pilot.press("f2")
            assert area.text == "bad"
            assert area.cursor_location == cursor
            assert area.history.undo_stack == history
            assert str(app.query_one("#diagnostic", Static).content) == "Use good"
            await pilot.press("f7", "g", "o", "o", "d", "f2")
        assert app.return_value == EditResult("accepted", "good")
    asyncio.run(exercise())


def test_discard_refusal_and_confirmation():
    async def exercise():
        app = EditorApp("seed")
        async with app.run_test() as pilot:
            await pilot.press("x", "escape")
            assert isinstance(app.screen, DiscardDialog)
            await pilot.click("#keep")
            assert app.query_one(TextArea).text == "xseed"
            await pilot.press("escape")
            await pilot.click("#discard")
        assert app.return_value == EditResult("cancelled")
    asyncio.run(exercise())


def test_find_paste_selection_undo_redo_and_resize():
    from textual.events import Paste

    async def exercise():
        app = EditorApp("alpha beta")
        async with app.run_test() as pilot:
            await pilot.press("f4")
            app.query_one("#find", Input).value = "beta"
            await pilot.press("enter")
            area = app.query_one(TextArea)
            assert area.selected_text == "beta"
            assert area.text == "alpha beta"
            await pilot.press("escape", "left", "shift+right")
            assert area.selected_text == "b"
            app.post_message(Paste("B"))
            await pilot.pause()
            assert area.text == "alpha Beta"
            await pilot.press("ctrl+z")
            assert area.text == "alpha beta"
            await pilot.press("ctrl+y")
            assert area.text == "alpha Beta"
            await pilot.resize_terminal(40, 12)
            assert area.text == "alpha Beta"
            await pilot.press("f2")
        assert app.return_value == EditResult("accepted", "alpha Beta")
    asyncio.run(exercise())


def test_cancel_unchanged():
    async def exercise():
        app = EditorApp("seed")
        async with app.run_test() as pilot:
            await pilot.press("escape")
        assert app.return_value == EditResult("cancelled")
    asyncio.run(exercise())


def test_unexpected_validator_error_is_not_acceptance():
    def fail(text):
        raise RuntimeError("validator failed")

    async def exercise():
        app = EditorApp("seed", validator=fail)
        async with app.run_test() as pilot:
            await pilot.press("f2")
        assert isinstance(app.failure, RuntimeError)
        assert app.return_value == EditResult("cancelled")
    asyncio.run(exercise())


def test_noninteractive_and_mixed_endings_fail_before_launch():
    with pytest.raises(ValueError, match="line endings"):
        edit_text("a\r\nb\nc")
    with pytest.raises(RuntimeError, match="interactive terminal"):
        edit_text("seed")


def test_import_does_not_load_textual():
    result = subprocess.run(
        [sys.executable, "-c", "import edital; import sys; assert 'textual' not in sys.modules; assert 'confease' not in sys.modules"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
