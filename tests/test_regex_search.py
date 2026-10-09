"""Regex behavior through the shared panel in both real application adapters."""

import asyncio

import pytest
from textual.document._document import Selection
from textual.widgets import Button, Input, Static, TextArea

from edital import Edital, EditResult
from edital.app import EditorApp
from edital.controls import HelpDialog
from edital.file_app import FileEditorApp
from edital.search import SearchPanel


@pytest.fixture(params=["embedded", "standalone"])
def editor_app(request):
    def create(text):
        if request.param == "embedded":
            return EditorApp(text), None
        editor = Edital()
        document = editor.new()
        document.text = document.baseline = text
        document.newline = "\r\n" if "\r\n" in text else "\n"
        return FileEditorApp(editor), document
    return create


def query(panel, term, replacement=""):
    panel.query_one("#find", Input).value = term
    panel.query_one("#replacement", Input).value = replacement


def report(panel):
    return str(panel.query_one("#search-result", Static).content)


def test_toggle_keyboard_retention_narrow_layout_and_literal_default(editor_app):
    async def exercise():
        app, document = editor_app("a.a aba")
        async with app.run_test(size=(30, 16)) as pilot:
            await pilot.press("f4")
            panel, area = app.query_one(SearchPanel), app.query_one(TextArea)
            button = panel.query_one("#regex-toggle", Button)
            assert not panel.regex and str(button.label) == "Regex: OFF"
            assert button.region.right <= 30 and button.region.width == 12
            assert panel.query_one("#find").region.width > 0
            query(panel, "a.a", r"\g<1>")
            panel.find_next()
            assert area.selected_text == "a.a" and "1 matches" in report(panel)
            await pilot.press("tab", "enter")
            assert app.focused is button and panel.regex
            assert str(button.label) == "Regex: ON" and button.variant == "primary"
            assert panel.match is None and report(panel) == ""
            assert "Python regex" in panel.query_one("#find", Input).placeholder
            panel.find_next()
            assert "2 matches" in report(panel)
            await pilot.press("escape", "f5")
            assert panel.regex and panel.query_one("#replacement", Input).value == r"\g<1>"
            assert panel.query_one("#replacement").display
            await pilot.press("f1")
            assert isinstance(app.screen, HelpDialog)
            assert r"\g<name>" in app.screen.text
            await pilot.press("escape", "f4")
            assert panel.regex and not panel.query_one("#replacement").display
            panel.toggle_regex()
            panel.replace_all()
            assert area.text == r"\g<1> aba"
            if document is not None:
                second = app.editor.new()
                second.text = "a.a"
                await app.reconcile()
                await pilot.pause()
                panel.toggle_regex()
                panel.find_next()
                await pilot.press("ctrl+pageup")
                assert panel.regex and panel.match is None
                query(panel, "a.a", "z")
                panel.replace_one()  # Tab changes never authorize a stale replacement.
                assert area.text == r"\g<1> aba"
                panel.replace_all()
                await pilot.pause()
                assert second.text == "a.a" and document.text == r"\g<1> z"
    asyncio.run(exercise())


def test_capture_replacement_single_and_all(editor_app):
    async def exercise():
        app, _ = editor_app("Doe, Jane\nSmith, John")
        async with app.run_test() as pilot:
            await pilot.press("f5")
            panel, area = app.query_one(SearchPanel), app.query_one(TextArea)
            panel.toggle_regex()
            query(panel, r"(?P<last>\w+),\s*(\w+)", r"\g<2> \g<last>")
            panel.replace_one()
            assert area.text == "Doe, Jane\nSmith, John" and area.selected_text == "Doe, Jane"
            panel.replace_one()
            assert area.text == "Jane Doe\nSmith, John" and area.selected_text == "Smith, John"
            panel.replace_all()
            assert area.text == "Jane Doe\nJohn Smith" and "1 replacements" in report(panel)
            query(panel, r"\w+", "")
            panel.replace_all()
            assert area.text == " \n " and "4 replacements" in report(panel)
    asyncio.run(exercise())


@pytest.mark.parametrize("width", [30, 80])
def test_search_control_geometry_stays_fixed_on_focus_and_press(editor_app, width):
    async def exercise():
        app, _ = editor_app("a a")
        async with app.run_test(size=(width, 24)) as pilot:
            await pilot.press("f5")
            panel = app.query_one(SearchPanel)
            query(panel, "a", "a")
            panel.find_next()
            await pilot.pause()
            buttons = list(panel.query(Button))
            inputs = list(panel.query(Input))

            def geometry():
                # Result feedback may change the panel's overall screen position.
                return {item.id: (item.region.x, item.region.y - panel.region.y,
                                  item.region.width, item.region.height)
                        for item in [*inputs, *buttons, panel.query_one("#search-query"),
                                     panel.query_one("#search-actions")]}

            regions = geometry()
            for field in inputs:
                assert field.region.height == field.content_region.height == 1
                assert field.content_region.x == field.region.x + 2
                assert field.content_region.right == field.region.right - 2
                field.value = ""
                await pilot.click(f"#{field.id}")
                await pilot.press("a")
                assert app.focused is field and field.value == "a"
                assert field.content_region.x == field.region.x + 2
                assert geometry() == regions
            for button in buttons:
                assert button.region.height == 1
                button.focus()
                await pilot.pause()
                assert geometry() == regions
                await pilot.click(f"#{button.id}")
                # Check during the pressed animation as well as after it clears.
                for delay in (0, button.active_effect_duration + 0.05):
                    await pilot.pause(delay)
                    assert geometry() == regions
                    assert button.content_region.height == 1
            toggle = panel.query_one("#regex-toggle", Button)
            assert toggle.content_region.width >= len("Regex: OFF")
            assert str(toggle.label) == "Regex: ON"
            assert toggle.variant == "primary"
            await pilot.press("f4")
            assert not panel.query_one("#replacement").display
            assert panel.query_one("#find").region.height == 1
            assert panel.query_one("#find").region.y == toggle.region.y
            await pilot.press("f5")
            assert geometry() == regions
    asyncio.run(exercise())


def test_anchors_case_flags_dot_and_count(editor_app):
    async def exercise():
        app, _ = editor_app("item\nITEM\nend")
        async with app.run_test() as pilot:
            await pilot.press("f4")
            panel, area = app.query_one(SearchPanel), app.query_one(TextArea)
            panel.toggle_regex()
            query(panel, "^item")
            panel.find_next()
            assert area.selected_text == "item" and "1 matches" in report(panel)
            query(panel, "(?i)^item")
            panel.find_next()
            assert area.selected_text == "ITEM" and "2 matches" in report(panel)
            panel.find_next()
            assert area.selection.start == (0, 0)
            query(panel, "item.*end")
            panel.find_next()
            assert "not found" in report(panel)
            query(panel, "(?s)item.*end", "x")
            panel.find_next()
            assert area.selected_text == "item\nITEM\nend"
            panel.replace_all()
            assert area.text == "x" and "1 replacements" in report(panel)
    asyncio.run(exercise())


@pytest.mark.parametrize("pattern,text,positions", [
    ("^", "a\nb", [(0, 0), (1, 0)]),
    ("$", "a\nb", [(0, 1), (1, 1)]),
    ("(?=a)", "aa", [(0, 0), (0, 1)]),
    ("$", "", [(0, 0)]),
    ("(?=a)|a", "a", [(0, 0), (0, 0)]),
])
def test_zero_width_navigation(editor_app, pattern, text, positions):
    async def exercise():
        app, _ = editor_app(text)
        async with app.run_test() as pilot:
            await pilot.press("f5")
            panel, area = app.query_one(SearchPanel), app.query_one(TextArea)
            panel.toggle_regex()
            query(panel, pattern)
            for index, position in enumerate(positions):
                panel.find_next()
                assert area.selection.start == position
                assert panel.match.ordinal == index
                assert f"{len(positions)} matches" in report(panel)
                if index == 0:
                    assert "Zero-width" in report(panel)
                    assert f"line {position[0] + 1}, column {position[1] + 1}" in report(panel)
            panel.find_next()
            assert panel.match.ordinal == 0 and area.text == text
    asyncio.run(exercise())


@pytest.mark.parametrize("pattern,text,replacement,result,count", [
    ("^", "a\nb", "> ", "> a\n> b", 2),
    ("$", "", "x", "x", 1),
    ("(?=a)|a", "a", "x", "xx", 2),
    ("x*", "ab", "-", "-a-b-", 3),
    ("(a)", "a a", r"\g<1>\g<1>", "aa aa", 2),
    ("(a)", "a", r"\g<1>\n", "a\n", 1),
    ("(?=a)", "aa", "", "aa", 2),
])
def test_zero_width_and_snapshot_replace_all(editor_app, pattern, text, replacement, result, count):
    async def exercise():
        app, _ = editor_app(text)
        async with app.run_test() as pilot:
            await pilot.press("f5")
            panel, area = app.query_one(SearchPanel), app.query_one(TextArea)
            panel.toggle_regex()
            query(panel, pattern, replacement)
            panel.replace_all()
            assert area.text == result and f"{count} replacements" in report(panel)
            await pilot.press("escape", "ctrl+z")
            assert area.text == text
            if result != text:
                await pilot.press("ctrl+y")
                assert area.text == result
    asyncio.run(exercise())


@pytest.mark.parametrize("pattern,text,replacement,position,selected", [
    ("^", "a\nb", "> ", (1, 0), ""),
    ("(?=a)", "aa", "", (0, 1), ""),
    ("(?=a)|a", "a", "", (0, 0), "a"),
    ("(?=a)", "aa", "x", (0, 2), ""),
    ("$", "", "x", (0, 1), ""),
])
def test_replace_one_zero_width_progress(editor_app, pattern, text, replacement, position, selected):
    async def exercise():
        app, _ = editor_app(text)
        async with app.run_test() as pilot:
            await pilot.press("f5")
            panel, area = app.query_one(SearchPanel), app.query_one(TextArea)
            panel.toggle_regex()
            query(panel, pattern, replacement)
            panel.find_next()
            panel.replace_one()
            assert area.selection.start == position and area.selected_text == selected
            assert area.text == replacement + text
    asyncio.run(exercise())


def test_errors_staleness_and_history_are_atomic(editor_app):
    async def exercise():
        app, _ = editor_app("a a")
        async with app.run_test() as pilot:
            area = app.query_one(TextArea)
            await pilot.press("x", "f5")
            panel = app.query_one(SearchPanel)
            panel.toggle_regex()
            for pattern, replacement, diagnostic in [
                ("", "", "nonempty"),
                ("(", "", "Invalid regex"),
                ("(a)", r"\g<2>", "Invalid replacement"),
                ("(missing)", r"\g<2>", "Invalid replacement"),
                ("(missing)", r"\g<absent>", "Invalid replacement"),
                ("(missing)", r"\q", "Invalid replacement"),
                ("(missing)", "\\", "Invalid replacement"),
            ]:
                query(panel, pattern, replacement)
                if not pattern or pattern == "(":
                    panel.find_next()
                    assert diagnostic in report(panel)
                for action in (panel.replace_one, panel.replace_all):
                    action()
                    assert diagnostic in report(panel) and area.text == "xa a"
            query(panel, "(a)", r"\g<2>")
            panel.find_next()
            assert area.selected_text == "a"  # Invalid template does not block Find.
            query(panel, "(a)", "z")
            area.selection = Selection((0, 0), (0, 1))
            panel.replace_one()
            assert area.text == "xa a" and area.selected_text == "a"
            query(panel, "a", "z")  # Changed pattern invalidates capture match.
            panel.replace_one()
            assert area.text == "xa a"
            panel.toggle_regex()
            panel.replace_one()
            assert area.text == "xa a"
            area.insert("!", (0, 0))  # Snapshot mutation invalidates selection authorization.
            panel.replace_one()
            assert area.text == "!xa a"
            await pilot.press("escape", "ctrl+z", "ctrl+z")
            assert area.text == "a a"  # Errors/toggles added no history entries.
    asyncio.run(exercise())


def test_unchanged_replacements_preserve_previous_undo(editor_app):
    async def exercise():
        app, _ = editor_app("a")
        async with app.run_test() as pilot:
            await pilot.press("x", "f5")
            panel, area = app.query_one(SearchPanel), app.query_one(TextArea)
            panel.toggle_regex()
            query(panel, "(a)", r"\g<1>")
            panel.find_next()
            panel.replace_one()
            panel.replace_all()
            query(panel, "^", "")
            panel.replace_all()
            assert area.text == "xa"
            await pilot.press("escape", "ctrl+z")
            assert area.text == "a"  # No-op replacements must not consume an undo step.
    asyncio.run(exercise())


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("trailing", [False, True])
def test_regex_history_newline_fidelity_and_dirty_state(editor_app, newline, trailing, user_storage):
    async def exercise():
        original = newline.join(["a", "a"]) + (newline if trailing else "")
        app, document = editor_app(original)
        async with app.run_test() as pilot:
            area = app.query_one(TextArea)
            await pilot.press("x", "f5")
            panel = app.query_one(SearchPanel)
            panel.toggle_regex()
            query(panel, "(a)", r"\g<1>\g<1>")
            panel.replace_all()
            await pilot.pause()
            expected = "x" + original.replace("a", "aa")
            assert area.text == expected.replace("\r\n", "\n")
            if document is None:
                assert app.candidate == expected and not user_storage[0].exists()
            else:
                assert document.text == expected and document.modified
            await pilot.press("escape", "ctrl+z")
            assert area.text == "x" + original.replace("\r\n", "\n")
            await pilot.press("ctrl+z")
            await pilot.pause()
            assert area.text == original.replace("\r\n", "\n")
            if document is not None:
                assert not document.modified
            await pilot.press("ctrl+y", "ctrl+y")
            assert area.text == expected.replace("\r\n", "\n")
    asyncio.run(exercise())


@pytest.mark.parametrize("accept", [True, False])
def test_embedded_regex_replacement_respects_validation_and_cancel(accept, user_storage):
    async def exercise():
        app = EditorApp("a", validator=lambda text: "Rejected" if text != "good" else None)
        async with app.run_test() as pilot:
            await pilot.press("f5")
            panel = app.query_one(SearchPanel)
            panel.toggle_regex()
            query(panel, "(a)", r"\g<1>\g<1>")
            panel.replace_all()
            await pilot.press("escape", "f3")
            assert app.is_running and "Rejected" in str(app.query_one("#diagnostic", Static).content)
            if accept:
                await pilot.press("f5")
                query(panel, "aa", "good")
                panel.replace_all()
                await pilot.press("escape", "f3")
            else:
                await pilot.press("escape", "tab", "enter")
        assert app.return_value == (EditResult("accepted", "good") if accept else EditResult("cancelled"))
        assert not user_storage[0].exists() and not user_storage[1].exists()
    asyncio.run(exercise())
