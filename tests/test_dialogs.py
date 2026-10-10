"""Verify compact prompt geometry and keyboard behavior in both editor modes."""

import asyncio

import pytest
from textual.widgets import Button, Input, TextArea

from edital import Edital, EditResult
from edital.app import DialogActions, DiscardDialog, EditorApp
from edital.file_app import FileEditorApp, PathDialog


def assert_actions_fit(dialog, container_id, narrow):
    container = dialog.query_one(container_id)
    assert container.region.width <= dialog.size.width
    row = dialog.query_one(DialogActions)
    buttons = list(row.query(Button))
    assert row.has_class("-stacked") is narrow
    for button in buttons:
        assert button.region.height == 1
        assert container.region.contains_region(button.region)
        assert button.region.width < container.region.width
    if narrow:
        assert buttons[0].region.y < buttons[1].region.y
    else:
        assert buttons[0].region.y == buttons[1].region.y
        assert buttons[0].region.right <= buttons[1].region.x
    return container.region.width


@pytest.mark.parametrize("width", [24, 80])
def test_standalone_prompts_fit_and_retain_behavior(tmp_path, width):
    async def exercise():
        editor = Edital()
        document = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test(size=(width, 24)) as pilot:
            await pilot.press("x", "ctrl+w")
            dialog = app.screen
            assert isinstance(dialog, DiscardDialog)
            assert dialog.focused.id == "keep"
            discard_width = assert_actions_fit(dialog, "#discard-dialog", width == 24)
            await pilot.press("enter")
            assert editor.files == (document,) and app.areas[document.id].text == "x"
            await pilot.press("ctrl+s")
            assert isinstance(app.screen, PathDialog)
            path_width = assert_actions_fit(app.screen, "#path-dialog", width == 24)
            assert path_width >= discard_width
            if width == 80:
                assert path_width > discard_width
            assert isinstance(app.screen.focused, Input)
            await pilot.press("escape")
            assert document.path is None and document.text == "x"
            await pilot.press("ctrl+s")
            app.screen.query_one(Input).value = str(tmp_path / "saved")
            await pilot.press("enter")
            assert document.path.read_text() == "x"
            await pilot.press("ctrl+o")
            await pilot.click("#cancel")
            assert app.screen is app.screen_stack[0] and editor.files == (document,)
    asyncio.run(exercise())


@pytest.mark.parametrize("width", [24, 80])
def test_embedded_compact_discard_preserves_state_and_no_config(user_storage, width):
    async def exercise():
        app = EditorApp("seed")
        async with app.run_test(size=(width, 24)) as pilot:
            await pilot.press("x", "shift+right")
            area = app.query_one(TextArea)
            selection, history = area.selection, list(area.history.undo_stack)
            await pilot.press("ctrl+q")
            assert isinstance(app.screen, DiscardDialog)
            assert_actions_fit(app.screen, "#discard-dialog", width == 24)
            await pilot.press("enter")
            assert area.text == "xseed" and area.selection == selection
            assert area.history.undo_stack == history
            await pilot.press("ctrl+q", "escape")
            assert area.text == "xseed"
            await pilot.press("ctrl+q")
            await pilot.click("#discard")
        assert app.return_value == EditResult("cancelled")
        assert not user_storage[0].exists()
    asyncio.run(exercise())


def test_prompt_actions_reflow_after_resize():
    async def exercise():
        app = EditorApp("seed")
        async with app.run_test() as pilot:
            await pilot.press("x", "ctrl+q")
            assert_actions_fit(app.screen, "#discard-dialog", False)
            await pilot.resize_terminal(24, 18)
            assert_actions_fit(app.screen, "#discard-dialog", True)
            await pilot.resize_terminal(80, 24)
            assert_actions_fit(app.screen, "#discard-dialog", False)
            await pilot.press("enter", "f2")
        assert app.return_value == EditResult("accepted", "xseed")
    asyncio.run(exercise())
