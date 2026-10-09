"""Shared literal/regex current-document search and undoable replacement panel."""

import re
from dataclasses import dataclass

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


@dataclass(frozen=True)
class SearchMatch:
    """An owned match from an immutable buffer snapshot."""

    area: TextArea
    text: str
    term: str
    regex: bool
    ordinal: int
    found: re.Match[str]

    @property
    def selection(self) -> Selection:
        return Selection(location(self.text, self.found.start()), location(self.text, self.found.end()))


class SearchPanel(Vertical):
    """Find/select matches and edit only the currently attached buffer."""

    DEFAULT_CSS = """
    SearchPanel { height: auto; max-height: 50%; overflow-y: auto; }
    SearchPanel Input.-textual-compact { height: 1; padding: 0 2; }
    SearchPanel Button { height: 1; border: none !important; padding: 0; }
    #search-query { height: 1; }
    #search-query Input { width: 1fr; min-width: 1; }
    #regex-toggle { width: 12; min-width: 12; padding: 0; }
    #search-actions { height: auto; layout: horizontal; }
    #search-actions Button { min-width: 0; width: 1fr; padding: 0; }
    #search-result { height: auto; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__(id="search")
        self.area: TextArea | None = None
        self.regex = False
        self.match: SearchMatch | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="search-query"):
            yield Input(placeholder="Find (literal, case-sensitive); Enter finds next", id="find",
                        compact=True)
            yield Button("Regex: OFF", id="regex-toggle", compact=True)
        yield Input(placeholder="Replace with (empty deletes matches)", id="replacement", compact=True)
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

    def toggle_regex(self) -> None:
        """Change query interpretation without editing or reusing an old match."""
        self.regex = not self.regex
        self.match = None
        button = self.query_one("#regex-toggle", Button)
        button.label = "Regex: ON" if self.regex else "Regex: OFF"
        button.variant = "primary" if self.regex else "default"
        self.query_one("#find", Input).placeholder = (
            "Find (Python regex); Enter finds next" if self.regex
            else "Find (literal, case-sensitive); Enter finds next"
        )
        self.query_one("#replacement", Input).placeholder = (
            r"Replace (captures: \g<1>, \g<name>; empty deletes)" if self.regex
            else "Replace with (empty deletes matches)"
        )
        self.report("")

    def term(self) -> str:
        term = self.query_one("#find", Input).value
        if not term:
            self.report("Enter nonempty text to find.")
        return term

    def pattern(self) -> re.Pattern[str] | None:
        """Compile the current query, reporting invalid input without edits."""
        term = self.term()
        if not term:
            self.match = None
            return None
        try:
            return re.compile(term if self.regex else re.escape(term), re.MULTILINE)
        except re.error as error:
            self.match = None
            self.report(f"Invalid regex: {error}")
            return None

    def valid_match(self, term: str) -> bool:
        match = self.match
        return (match is not None and match.area is self.area and match.text == match.area.text
                and match.term == term and match.regex == self.regex
                and match.area.selection == match.selection)

    def find_next(self, start: int | None = None, *, skip_empty: bool = False) -> None:
        area, pattern = self.area, self.pattern()
        if area is None or pattern is None:
            return
        text = area.text
        term = self.query_one("#find", Input).value
        matches = list(pattern.finditer(text))
        if not matches:
            self.match = None
            self.report("Text not found")
            return
        if start is None and self.valid_match(term) and self.match is not None:
            ordinal = (self.match.ordinal + 1) % len(matches)
        else:
            if start is None:
                start = offset(text, area.selection.end)
            ordinal = next((i for i, found in enumerate(matches)
                            if found.start() >= start
                            and not (skip_empty and found.start() == found.end() == start)), 0)
        found = matches[ordinal]
        self.match = SearchMatch(area, text, term, self.regex, ordinal, found)
        area.selection = self.match.selection
        area.scroll_cursor_visible(center=True)
        detail = "Match found"
        if found.start() == found.end():
            row, column = location(text, found.start())
            detail = f"Zero-width match at line {row + 1}, column {column + 1}"
        self.report(f"{detail} · {len(matches)} matches in current document")

    def replacement(self, pattern: re.Pattern[str]) -> str | None:
        """Validate a regex template even when the document has no matches."""
        replacement = self.query_one("#replacement", Input).value
        if self.regex:
            try:
                pattern.sub(replacement, "")
            except (re.error, IndexError) as error:
                self.report(f"Invalid replacement: {error}")
                return None
        return replacement

    def replace_one(self) -> None:
        area, pattern = self.area, self.pattern()
        if area is None or pattern is None:
            return
        replacement = self.replacement(pattern)
        if replacement is None:
            return
        term = self.query_one("#find", Input).value
        match = self.match
        if match is None or not self.valid_match(term):
            self.match = None
            self.find_next()
            return
        if self.regex:
            replacement = match.found.expand(replacement)
        expected = match.selection
        if replacement != match.found.group():
            area.history.checkpoint()
            area.replace(replacement, expected.start, expected.end, maintain_selection_offset=False)
            area.history.checkpoint()
        self.match = None
        self.find_next(match.found.start() + len(replacement),
                       skip_empty=match.found.start() == match.found.end())

    def replace_all(self) -> None:
        area, pattern = self.area, self.pattern()
        if area is None or pattern is None:
            return
        replacement = self.replacement(pattern)
        if replacement is None:
            return
        original = area.text
        if self.regex:
            result, count = pattern.subn(replacement, original)
        else:
            result, count = pattern.subn(lambda _: replacement, original)
        if result != original:
            area.history.checkpoint()
            area.replace(result, (0, 0), area.document.end,
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
        elif event.button.id == "regex-toggle":
            self.toggle_regex()
