"""Verify tab mouse dispatch and independent document-state styling."""

import asyncio
from types import SimpleNamespace

import pytest
from textual.color import Color
from textual.widgets import Button, Input, Tabs

from edital import Edital
from edital.app import DiscardDialog
from edital.file_app import FileEditorApp, PathDialog
from edital.tabs import DocumentTab, close_glyph


@pytest.mark.parametrize("conflict", [False, True])
def test_inactive_close_confirmation_preserves_selection(conflict):
    async def exercise():
        editor = Edital()
        inactive, active = editor.new(), editor.new()
        inactive.text = "unsaved"
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("a", "b", "shift+left")
            area = app.areas[active.id]
            selection, history = area.selection, list(area.history.undo_stack)
            inactive.conflict = conflict
            app.update_labels()
            await pilot.pause()
            tab = app.query_one(f"#tab-{inactive.id}", DocumentTab)
            assert tab.label.plain.startswith("▲ ⏺ " if conflict else "⏺ ")
            await pilot.click(tab, offset=(tab.close_offset, 0), button=3)
            assert inactive in editor.files and editor.session.active is active
            await pilot.click(tab, offset=(tab.close_offset, 0))
            assert isinstance(app.screen, DiscardDialog)
            assert editor.session.active is active
            await pilot.click("#keep")
            assert inactive in editor.files and editor.session.active is active
            assert area.selection == selection and area.history.undo_stack == history
            await pilot.click(tab, offset=(tab.close_offset, 0))
            await pilot.click("#discard")
            assert editor.files == (active,) and editor.session.active is active
            assert area.selection == selection and area.history.undo_stack == history
            assert not editor.cache
    asyncio.run(exercise())


@pytest.mark.parametrize("fallback", [False, True])
def test_name_click_close_scroll_and_final_tab(tmp_path, monkeypatch, fallback):
    if fallback:
        monkeypatch.setattr("edital.tabs.close_glyph", lambda: "X")
    async def exercise():
        editor = Edital(prompt=False)
        documents = editor.open(*(tmp_path / f"文件-{i}.txt" for i in range(8)))
        app = FileEditorApp(editor)
        async with app.run_test(size=(44, 20)) as pilot:
            await pilot.pause(0.3)
            last = app.query_one(f"#tab-{documents[-1].id}", DocumentTab)
            assert app.query_one("#tabs-scroll").scroll_x > 0
            await pilot.click(last, offset=(last.close_offset, 0))
            assert documents[-1] not in editor.files
            assert editor.session.active is documents[-2]
            await pilot.press("ctrl+pageup")
            assert editor.session.active is documents[-3]
            # Restore the first tab into view, then click its name to select it.
            first = app.query_one(f"#tab-{documents[0].id}", DocumentTab)
            first.scroll_visible(animate=False, force=True)
            await pilot.pause()
            await pilot.click(first, offset=(2, 0))
            assert editor.session.active is documents[0]
            await pilot.press("x")
            assert first.label.plain.startswith("⏺ ")
            await pilot.click(first, offset=(first.close_offset, 0))
            assert documents[0] not in editor.files  # dirty close with prompts disabled
            while editor.files:
                tab = app.query_one(f"#tab-{editor.session.active.id}", DocumentTab)
                tab.scroll_visible(animate=False, force=True)
                await pilot.pause()
                await pilot.click(tab, offset=(tab.close_offset, 0))
            assert not editor.exited and app.query_one("#empty").display
    asyncio.run(exercise())


def test_clean_inactive_close_and_failed_close(tmp_path, monkeypatch):
    async def exercise():
        path = tmp_path / "saved"
        path.write_text("saved")
        editor = Edital()
        inactive, = editor.open(path)
        active = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            tab = app.query_one(f"#tab-{inactive.id}", DocumentTab)
            original = editor.close

            def fail(document):
                raise OSError("close failed")

            monkeypatch.setattr(editor, "close", fail)
            await pilot.click(tab, offset=(tab.close_offset, 0))
            assert editor.files == (inactive, active) and editor.session.active is active
            assert "close failed" in str(app.query_one("#diagnostic").render())
            monkeypatch.setattr(editor, "close", original)
            await pilot.click(tab, offset=(tab.close_offset, 0))
            assert editor.files == (active,) and editor.session.active is active
    asyncio.run(exercise())


def test_close_glyph_fallbacks(monkeypatch):
    from edital import tabs
    monkeypatch.setattr(tabs.sys, "stdout", SimpleNamespace(encoding="ascii"))
    assert close_glyph() == "X"
    tab = DocumentTab("literal [name]", "document")
    assert tab.label.plain == "literal [name]  X"
    monkeypatch.setattr(tabs.sys, "stdout", SimpleNamespace(encoding="utf-8"))
    assert close_glyph() == "⨯"
    monkeypatch.setattr(tabs, "cell_len", lambda text: 2)
    assert close_glyph() == "X"


def test_first_save_dirty_undo_and_color_precedence(tmp_path):
    async def exercise():
        editor = Edital(draft_color="#FFA62B", conflict_color="#E06C75")
        unnamed = editor.new()
        named, = editor.open(tmp_path / "named")
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            tab = app.query_one(f"#tab-{named.id}", DocumentTab)
            other = app.query_one(f"#tab-{unnamed.id}", DocumentTab)
            assert tab.styles.color == Color.parse("#FFA62B")
            assert other.styles.color == Color.parse("#FFA62B").with_alpha(0.5)
            label = tab.label.plain
            await pilot.press("ctrl+s")
            assert named.path.exists() and named.autosave_eligible
            assert tab.label.plain == label and not tab.has_class("state-draft")
            await pilot.press("x")
            assert tab.label.plain.startswith("⏺ named")
            await pilot.press("ctrl+z")
            assert tab.label.plain == label
            # Make a conflicted draft without invoking startup recovery.
            unnamed.conflict = True
            unnamed.text = "changed"
            app.areas[unnamed.id].load_text("changed")
            app.update_labels()
            await pilot.press("ctrl+pageup")
            assert other.label.plain.startswith("▲ ⏺ draft")
            assert other.styles.color == Color.parse("#E06C75")
            await pilot.press("ctrl+pagedown")
            assert other.styles.color == Color.parse("#E06C75").with_alpha(0.5)
            await pilot.press("ctrl+pageup")
            tabs = app.query_one(Tabs)
            tabs.focus()
            await pilot.pause()
            await pilot.hover(other)
            assert other.styles.color == Color.parse("#E06C75")
            editor.conf.set("conflict_color", None)
            await pilot.pause()
            assert other.styles.color == Color.parse("#FFA62B")
            assert "▲" in other.label.plain
            editor.conf.set("draft_color", None)
            await pilot.pause()
            assert not other.has_class("state-draft") and not other.has_class("state-conflict")
            assert "▲ ⏺" in other.label.plain
            editor.conf.set("conflict_color", "#FF1122")
            await pilot.pause()
            assert other.styles.color == Color.parse("#FF1122")
            unnamed.conflict = False
            app.update_labels()
            await pilot.pause()
            assert "▲" not in other.label.plain and "⏺" in other.label.plain
            assert not other.has_class("state-conflict")
    asyncio.run(exercise())


def test_failed_first_save_keeps_draft_color(tmp_path):
    async def exercise():
        editor = Edital()
        document, = editor.open(tmp_path / "missing" / "file")
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            await pilot.press("x", "ctrl+s")
            tab = app.query_one(DocumentTab)
            assert not document.autosave_eligible and document.modified
            assert tab.styles.color == Color.parse(editor.conf.get("draft_color"))
            assert tab.label.plain.startswith("⏺ file")
    asyncio.run(exercise())


def test_focus_colors_update_open_prompts():
    async def exercise():
        editor = Edital(focus_color="#12AB34")
        document = editor.new()
        app = FileEditorApp(editor)
        async with app.run_test() as pilot:
            area = app.areas[document.id]
            assert area.styles.border_left[1] == Color.parse("#12AB34")
            underline = app.query_one("Underline")
            assert underline.get_component_styles("underline--bar").color == Color.parse("#12AB34")
            await pilot.press("f4")
            find = app.query_one("#find", Input)
            assert app.focused is find
            assert find.region.height == find.content_region.height == 1
            assert find.styles.gutter.height == 0  # Compact Find keeps focus without adding a border.
            await pilot.press("escape", "ctrl+o")
            assert isinstance(app.screen, PathDialog)
            field = app.screen.query_one(Input)
            assert field.styles.border_left[1] == Color.parse("#12AB34")
            editor.conf.set("focus_color", "#CC44AA")
            await pilot.pause()
            assert field.styles.border_left[1] == Color.parse("#CC44AA")
            button = app.screen.query_one("#continue", Button)
            button.focus()
            await pilot.pause()
            assert button.styles.border_left[1] == Color.parse("#CC44AA")
            await pilot.press("escape", "x", "ctrl+w")
            discard = app.screen.query_one("#discard", Button)
            before = discard.styles.background
            discard.focus()
            await pilot.pause()
            assert discard.styles.border_left[1] == Color.parse("#CC44AA")
            assert discard.styles.background == before
            await pilot.press("escape")
    asyncio.run(exercise())
