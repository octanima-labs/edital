"""Exercise tentative document navigation and modal session operations."""

import asyncio

import pytest
from textual.color import Color
from textual.widgets import Input, Static, TextArea

from edital import Edital
from edital.app import DiscardDialog, EditorApp
from edital.controls import HelpDialog
from edital.document_picker import DocumentPicker
from edital.file_app import FileEditorApp, PathDialog, RecoveryDialog
from edital.search import SearchPanel
from edital.tabs import DocumentTab


def test_picker_browsing_activation_and_scroll_preserve_editing_state():
    async def exercise():
        editor = Edital()
        documents = [editor.new() for _ in range(30)]
        app = FileEditorApp(editor)
        async with app.run_test(size=(44, 20)) as pilot:
            await pilot.press("x", "shift+left")
            area = app.areas[documents[-1].id]
            selection, history = area.selection, list(area.history.undo_stack)
            await pilot.press("f8")
            picker = app.screen
            assert isinstance(picker, DocumentPicker)
            assert picker.highlighted_id == documents[-1].id
            assert picker.order == [document.id for document in documents]
            assert picker.query_one("#picker-list").scroll_y > 0
            await pilot.press("f8")
            assert app.screen is picker and len(app.screen_stack) == 2
            await pilot.press("home", "up")
            assert picker.highlighted_id == documents[0].id
            assert editor.session.active is documents[-1]
            await pilot.press("pagedown")
            assert picker.highlighted_id != documents[0].id
            await pilot.press("pageup", "down")
            assert picker.highlighted_id == documents[1].id
            await pilot.press("end", "down")
            assert picker.highlighted_id == documents[-1].id
            assert picker.query_one("#picker-list").content_region.contains_region(
                picker.rows[documents[-1].id].region
            )
            await pilot.press("home", "enter")
            assert editor.session.active is documents[0]
            assert app.focused is app.areas[documents[0].id]
            assert area.selection == selection and area.history.undo_stack == history
            await pilot.press("f8", "end", "escape")
            assert editor.session.active is documents[0]
            assert app.focused is app.areas[documents[0].id]
    asyncio.run(exercise())


@pytest.mark.parametrize("prompt", [True, False])
def test_picker_close_targets_fallback_and_final_document(prompt):
    async def exercise():
        editor = Edital(prompt=prompt)
        first, second, third = editor.new(), editor.new(), editor.new()
        editor.session.active = first
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("x", "shift+left", "f8", "end")
            area = app.areas[first.id]
            selection, history = area.selection, list(area.history.undo_stack)
            picker = app.screen
            # Closing a different inactive row preserves both active and highlighted identities.
            await pilot.click(picker.rows[second.id].query_one(".picker-close"), button=3)
            assert editor.files == (first, second, third)
            await pilot.click(picker.rows[second.id].query_one(".picker-close"))
            assert app.screen is picker and editor.files == (first, third)
            assert editor.session.active is first and picker.highlighted_id == third.id
            assert area.selection == selection and area.history.undo_stack == history
            # Removing the last highlighted row selects its predecessor.
            await pilot.click(picker.rows[third.id].query_one(".picker-close"))
            assert app.screen is picker and picker.highlighted_id == first.id
            await pilot.click(picker.rows[first.id].query_one(".picker-close"))
            if prompt:
                assert isinstance(app.screen, DiscardDialog)
                await pilot.press("f8", "ctrl+shift+pageup", "escape")
                assert app.screen is picker and picker.highlighted_id == first.id
                assert editor.files == (first,)
                assert area.selection == selection and area.history.undo_stack == history
                assert app.focused is picker.query_one("#picker-list")
                await pilot.click(picker.rows[first.id].query_one(".picker-close"))
                await pilot.click("#discard")
            assert len(app.screen_stack) == 1 and not editor.files and not editor.exited
            assert app.screen.query_one("#empty").display
            assert not editor.cache
    asyncio.run(exercise())


@pytest.mark.parametrize("conflict", [False, True])
@pytest.mark.parametrize("keyboard", [False, True])
def test_picker_dirty_inactive_confirmation_and_active_neighbor(conflict, keyboard):
    async def exercise():
        editor = Edital()
        first, second, third = editor.new(), editor.new(), editor.new()
        second.text = "dirty"
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            second.conflict = conflict
            await pilot.press("f8", "home", "down")
            picker = app.screen
            if keyboard:
                await pilot.press("ctrl+w")
            else:
                await pilot.click(picker.rows[second.id].query_one(".picker-close"))
            assert isinstance(app.screen, DiscardDialog)
            assert editor.session.active is third
            await pilot.press("f1", "ctrl+shift+pageup", "ctrl+w", "escape")
            assert isinstance(app.screen, DiscardDialog) and editor.files == (first, second, third)
            await pilot.press("ctrl+w")
            assert editor.files == (first, second, third)
            await pilot.click("#keep")
            assert app.screen is picker and picker.highlighted_id == second.id
            assert editor.files == (first, second, third)
            if keyboard:
                await pilot.press("ctrl+w")
            else:
                await pilot.click(picker.rows[second.id].query_one(".picker-close"))
            await pilot.click("#discard")
            assert app.screen is picker and picker.highlighted_id == third.id
            assert editor.session.active is third and editor.files == (first, third)
            # Closing the active document uses the existing session neighbor rule.
            await pilot.click(picker.rows[third.id].query_one(".picker-close"))
            assert picker.highlighted_id == first.id and editor.session.active is first
            await pilot.press("escape")
            assert app.focused is app.areas[first.id]
            assert not editor.cache
    asyncio.run(exercise())


@pytest.mark.parametrize("keyboard", [False, True])
def test_picker_close_error_retry_and_busy_mutation_guard(monkeypatch, keyboard):
    async def exercise():
        editor = Edital()
        first, second = editor.new(), editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("f8", "home")
            picker = app.screen
            original = editor.close

            def fail(document):
                raise OSError("close failed")

            monkeypatch.setattr(editor, "close", fail)
            if keyboard:
                await pilot.press("ctrl+w")
            else:
                await pilot.click(picker.rows[first.id].query_one(".picker-close"))
            assert app.screen is picker and editor.files == (first, second)
            assert "close failed" in str(picker.query_one("#picker-error", Static).content)
            assert not picker.busy
            picker.busy = True
            await pilot.press("down", "enter", "ctrl+w", "ctrl+shift+pagedown", "escape")
            assert app.screen is picker and picker.highlighted_id == first.id
            assert editor.files == (first, second)
            picker.busy = False
            monkeypatch.setattr(editor, "close", original)
            if keyboard:
                await pilot.press("ctrl+w")
            else:
                await pilot.click(picker.rows[first.id].query_one(".picker-close"))
            assert app.screen is picker and editor.files == (second,)
            assert picker.highlighted_id == second.id and editor.session.active is second
            assert str(picker.query_one("#picker-error", Static).content) == ""
    asyncio.run(exercise())


@pytest.mark.parametrize("width,fallback", [(30, False), (80, False), (30, True)])
def test_picker_presentation_colors_layout_and_resize(tmp_path, monkeypatch, width, fallback):
    if fallback:
        monkeypatch.setattr("edital.document_picker.close_glyph", lambda: "X")

    async def exercise():
        editor = Edital(draft_color="#FFA62B", conflict_color="#E06C75", focus_color="#12AB34")
        # Same filename in different directories forces literal full-path disambiguation.
        first, second = editor.open(tmp_path / "one" / "文件-[red].txt", tmp_path / "two" / "文件-[red].txt")
        draft = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test(size=(width, 20)) as pilot:
            first.conflict = True
            app.areas[first.id].insert("changed", (0, 0))
            await pilot.press("f8", "home")
            picker = app.screen
            row = picker.rows[first.id]
            label = row.query_one(".picker-name", Static)
            close = row.query_one(".picker-close", Static)
            assert str(label.content) == app.label(first)
            assert str(label.content).startswith("▲ ⏺ ") and "[red]" in str(label.content)
            assert str(close.content) == ("X" if fallback else "⨯")
            assert row.styles.color == Color.parse("#E06C75")
            assert picker.rows[draft.id].styles.color == Color.parse("#FFA62B").with_alpha(0.5)
            panel = picker.query_one("#document-picker")
            assert panel.region.width <= width
            assert picker.query_one("#picker-title").region.height == 1
            assert row.region.height == close.region.height == label.region.height == 1
            assert close.region.right <= panel.content_region.right
            assert len(label.render_line(0).text) <= label.region.width
            geometry = row.region
            await pilot.hover(close)
            assert row.region == geometry
            await pilot.press("down", "up")
            assert row.region == geometry
            assert picker.highlighted_id == first.id and editor.session.active is draft
            editor.conf.set("conflict_color", None)
            await pilot.pause()
            assert row.styles.color == Color.parse("#FFA62B") and "▲" in str(label.content)
            editor.conf.set("draft_color", None)
            await pilot.pause()
            assert not row.has_class("state-draft") and not row.has_class("state-conflict")
            await pilot.press("f1")
            editor.conf.set("conflict_color", "#FF1122")
            editor.conf.set("focus_color", "#CC44AA")
            await pilot.pause()
            assert row.styles.color == Color.parse("#FF1122")
            await pilot.press("escape")
            assert panel.styles.border_left[1] == Color.parse("#CC44AA")
            await pilot.resize_terminal(32 if width == 80 else 60, 16)
            assert row.region.height == close.region.height == 1
            assert close.region.right <= panel.content_region.right
            assert picker.highlighted_id == first.id
            # Closing a duplicate updates the surviving document title in place.
            first.conflict = False
            editor.conf.set("prompt", False)
            await pilot.click(close)
            surviving = picker.rows[second.id].query_one(".picker-name", Static)
            assert str(surviving.content) == second.path.name
    asyncio.run(exercise())


def test_picker_live_autosave_retains_rows_and_scroll(tmp_path):
    async def exercise():
        path = tmp_path / "saved"
        path.write_text("saved")
        editor = Edital(auto_save=60000)
        saved, = editor.open(path)
        for _ in range(30):
            editor.new()
        app = FileEditorApp(editor)
        async with app.run_test(size=(40, 20)) as pilot:
            app.areas[saved.id].insert("x", (0, 0))
            await pilot.pause()
            await pilot.press("f8")
            picker = app.screen
            row = picker.rows[saved.id]
            assert "⏺" in str(row.query_one(".picker-name", Static).content)
            highlighted = picker.highlighted_id
            scroll = picker.query_one("#picker-list").scroll_y
            app._autosave()
            await pilot.pause()
            assert path.read_text() == "xsaved"
            assert "⏺" not in str(row.query_one(".picker-name", Static).content)
            assert picker.rows[saved.id] is row and picker.highlighted_id == highlighted
            assert picker.query_one("#picker-list").scroll_y == scroll
    asyncio.run(exercise())


def test_single_document_and_other_modals_still_block_picker_commands():
    async def exercise():
        editor = Edital()
        document = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("f8", "up", "down", "ctrl+shift+pageup", "ctrl+shift+pagedown")
            picker = app.screen
            assert picker.highlighted_id == document.id and editor.files == (document,)
            await pilot.press("escape", "ctrl+n", "ctrl+o")
            documents = editor.files
            assert len(documents) == 2
            assert isinstance(app.screen, PathDialog)
            dialog = app.screen
            await pilot.press("f8", "ctrl+shift+pageup")
            assert app.screen is dialog and editor.files == documents
            await pilot.press("escape")
            app.push_screen(RecoveryDialog(document))
            dialog = app.screen
            await pilot.press("f8", "ctrl+shift+pageup")
            assert app.screen is dialog and editor.files == documents
            await pilot.press("escape")
    asyncio.run(exercise())


def test_picker_search_focus_cancel_and_name_click():
    async def exercise():
        editor = Edital()
        first, second = editor.new(), editor.new()
        second.text = "a a"
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("f5")
            panel = app.query_one(SearchPanel)
            panel.toggle_regex()
            field = app.query_one("#find", Input)
            field.value = "a"
            panel.find_next()
            match = panel.match
            await pilot.press("f8", "home", "escape")
            assert app.focused is field and field.value == "a"
            assert panel.regex and panel.match is match and editor.session.active is second
            await pilot.press("f8")
            picker = app.screen
            row = picker.rows[first.id]
            await pilot.click(row.query_one(".picker-name"), button=3)
            assert app.screen is picker and editor.session.active is second
            await pilot.click(row.query_one(".picker-name"))
            assert editor.session.active is first and app.focused is app.areas[first.id]
            assert panel.match is None
    asyncio.run(exercise())


def test_picker_empty_workspace_and_embedded_reservation():
    async def exercise():
        editor = Edital()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("f8")
            assert len(app.screen_stack) == 1 and not editor.files
        embedded = EditorApp("seed")
        async with embedded.run_test() as pilot:
            await pilot.press("f8")
            assert embedded.query_one(TextArea).text == "seed"
            assert len(embedded.screen_stack) == 1
            await pilot.press("f1")
            assert isinstance(embedded.screen, HelpDialog)
            assert "f8: Documents — unavailable in embedded" in embedded.screen.text
        assert not editor.exited
    asyncio.run(exercise())


def test_picker_reorder_and_nested_help_isolation():
    async def exercise():
        editor = Edital()
        first, second, third = editor.new(), editor.new(), editor.new()
        editor.session.active = first
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("x", "f8", "down", "ctrl+shift+pagedown")
            picker = app.screen
            assert isinstance(picker, DocumentPicker)
            assert editor.files == (first, third, second)
            assert picker.order == [first.id, third.id, second.id]
            assert picker.highlighted_id == second.id and editor.session.active is first
            area = app.areas[first.id]
            selection, history = area.selection, list(area.history.undo_stack)
            assert [tab.document_id for tab in app.screen_stack[0].query(DocumentTab)] == picker.order
            original_rows = dict(picker.rows)
            assert app.focused is picker.query_one("#picker-list")
            await pilot.press("ctrl+shift+pagedown")
            assert editor.files == (first, third, second)
            await pilot.press("f2", "f3", "f4", "f5", "ctrl+n", "ctrl+o",
                              "ctrl+s", "ctrl+pageup", "ctrl+pagedown", "ctrl+q", "ctrl+p")
            assert app.screen is picker and editor.files == (first, third, second)
            assert app.areas[first.id].text == "x"
            await pilot.press("f1")
            assert isinstance(app.screen, HelpDialog)
            assert "f8: Documents" in app.screen.text
            await pilot.press("ctrl+shift+pageup", "ctrl+w", "escape")
            assert app.screen is picker and editor.files == (first, third, second)
            assert picker.highlighted_id == second.id
            assert all(picker.rows[identity] is row for identity, row in original_rows.items())
            assert area.selection == selection and area.history.undo_stack == history
            await pilot.press("escape")
            assert editor.session.active is first and editor.files == (first, third, second)
            await pilot.press("ctrl+pagedown")
            assert editor.session.active is third
    asyncio.run(exercise())


@pytest.mark.parametrize("prompt", [True, False])
def test_picker_ctrl_w_clean_and_final_close(prompt):
    async def exercise():
        editor = Edital(prompt=prompt)
        active, highlighted = editor.new(), editor.new()
        editor.session.active = active
        app = FileEditorApp(editor)
        async with app.run_test(size=(32, 20)) as pilot:
            await pilot.press("f8", "down", "ctrl+w")
            picker = app.screen
            assert isinstance(picker, DocumentPicker)
            assert editor.files == (active,) and editor.session.active is active
            assert highlighted.id not in picker.rows and picker.highlighted_id == active.id
            assert app.focused is picker.query_one("#picker-list")
            await pilot.press("ctrl+w")
            assert not editor.files and not editor.exited
            assert len(app.screen_stack) == 1 and app.screen.query_one("#empty").display
            assert not editor.cache
    asyncio.run(exercise())


def test_picker_active_close_restores_search_and_reorder_preserves_buffers():
    async def exercise():
        editor = Edital()
        first, second, third = editor.new(), editor.new(), editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("f5")
            panel = app.query_one(SearchPanel)
            panel.toggle_regex()
            field = app.query_one("#find", Input)
            field.value = "a"
            areas = dict(app.areas)
            histories = {identity: list(area.history.undo_stack) for identity, area in areas.items()}
            await pilot.press("f8", "home", "ctrl+shift+pagedown")
            picker = app.screen
            assert editor.files == (second, first, third) and editor.session.active is third
            assert all(app.areas[identity] is area for identity, area in areas.items())
            assert all(area.history.undo_stack == histories[identity] for identity, area in areas.items())
            await pilot.click(picker.rows[third.id].query_one(".picker-close"))
            assert editor.session.active is first and app.screen is picker
            await pilot.press("escape")
            assert app.focused is field and field.value == "a" and panel.regex
            assert panel.area is areas[first.id]
    asyncio.run(exercise())
