"""Shared literal current-document search and undoable replacement panel."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.document._document import Selection
from textual.widgets import Button, Input, Static, TextArea


def location(text: str, offset: int) -> tuple[int, int]:
    """Convert an LF buffer offset to an editor location."""
    return text.count("\n", 0, offset), offset - text.rfind("\n", 0, offset) - 1


def offset(text: str, point: tuple[int, int]) -> int:
    """Convert an editor location to an LF buffer offset."""
    row, column = point
    return sum(len(line) + 1 for line in text.split("\n")[:row]) + column


class SearchPanel(Vertical):
    """Find/select matches and edit only the currently attached buffer."""

    DEFAULT_CSS = """
    SearchPanel { height: auto; max-height: 50%; overflow-y: auto; }
    SearchPanel Input { height: 3; }
    #search-actions { height: auto; layout: horizontal; }
    #search-actions Button { min-width: 0; width: 1fr; padding: 0; }
    #search-result { height: auto; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__(id="search")
        self.area: TextArea | None = None
        self.match: tuple[TextArea, str, str, int, int] | None = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Find (literal, case-sensitive); Enter finds next", id="find")
        yield Input(placeholder="Replace with (empty deletes matches)", id="replacement")
        with Horizontal(id="search-actions"):
            yield Button("Find next", id="find-next", compact=True)
            yield Button("Replace", id="replace-one", compact=True)
            yield Button("Replace all", id="replace-all", compact=True)
        yield Static("", id="search-result", markup=False)

    def on_mount(self) -> None:
        self.display = False
        self.query_one("#find").display = False

    def attach(self, area: TextArea | None) -> None:
        if area is not self.area:
            self.match = None
        self.area = area

    def open(self, area: TextArea, *, replace: bool) -> None:
        self.attach(area)
        self.display = True
        self.query_one("#find").display = True
        for selector in ("#replacement", "#replace-one", "#replace-all"):
            self.query_one(selector).display = replace
        self.query_one("#find", Input).focus()

    def close(self) -> None:
        self.display = False
        self.query_one("#find").display = False
        if self.area is not None:
            self.area.focus()

    def report(self, text: str) -> None:
        self.query_one("#search-result", Static).update(text)

    def term(self) -> str:
        term = self.query_one("#find", Input).value
        if not term:
            self.report("Enter nonempty text to find.")
        return term

    def find_next(self, start: int | None = None) -> None:
        area, term = self.area, self.term()
        if area is None or not term:
            return
        text = area.text
        if start is None:
            start = offset(text, area.selection.end)
        index = text.find(term, start)
        if index < 0:
            index = text.find(term)
        if index < 0:
            self.match = None
            self.report("Text not found")
            return
        end = index + len(term)
        area.selection = Selection(location(text, index), location(text, end))
        area.scroll_cursor_visible(center=True)
        self.match = (area, text, term, index, end)
        self.report(f"Match found · {text.count(term)} matches in current document")

    def replace_one(self) -> None:
        area, term = self.area, self.term()
        if area is None or not term:
            return
        match = self.match
        if match is None:
            self.find_next()
            return
        owner, original, matched_term, start, end = match
        expected = Selection(location(original, start), location(original, end))
        if owner is not area or original != area.text or matched_term != term or area.selection != expected:
            self.match = None
            self.find_next()
            return
        replacement = self.query_one("#replacement", Input).value
        area.history.checkpoint()
        area.replace(replacement, expected.start, expected.end, maintain_selection_offset=False)
        area.history.checkpoint()
        self.match = None
        self.find_next(start + len(replacement))

    def replace_all(self) -> None:
        area, term = self.area, self.term()
        if area is None or not term:
            return
        original = area.text
        count = original.count(term)
        if count:
            replacement = self.query_one("#replacement", Input).value
            area.history.checkpoint()
            area.replace(original.replace(term, replacement), (0, 0), area.document.end,
                         maintain_selection_offset=False)
            area.history.checkpoint()
        self.match = None
        self.report(f"{count} replacements in current document")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.find_next()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "find-next":
            self.find_next()
        elif event.button.id == "replace-one":
            self.replace_one()
        elif event.button.id == "replace-all":
            self.replace_all()
