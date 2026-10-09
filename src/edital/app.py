"""Textual implementation of Edital's standalone text-session contract."""

from typing import ClassVar

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Static, TextArea

from .session import EditResult, Validator, line_ending


class DialogActions(Horizontal):
    """Content-sized, one-line actions with a narrow-width vertical fallback."""

    DEFAULT_CSS = """
    DialogActions {
        height: auto; margin-top: 1; align-horizontal: right;
        Button {
            width: auto; min-width: 0; max-width: 100%; margin-left: 1;
            border-left: blank transparent !important;
            border-right: blank transparent !important;
        }
        Button:focus {
            border-left: solid $border !important;
            border-right: solid $border !important;
        }
        &.-stacked {
            layout: vertical;
            Button { margin: 0 0 1 0; }
        }
    }
    """

    def on_resize(self, event: events.Resize) -> None:
        required = sum(button.get_content_width(event.size, self.screen.size)
                       + button.styles.gutter.width + 1 for button in self.query(Button))
        self.set_class(required > event.size.width, "-stacked")


class DiscardDialog(ModalScreen[bool]):
    """Ask whether to abandon a modified buffer."""

    DEFAULT_CSS = """
    DiscardDialog { align: center middle; background: $background 70%; }
    #discard-dialog {
        width: 40; max-width: 100%; height: auto; max-height: 100%;
        overflow-y: auto; padding: 1 2; border: thick $primary;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="discard-dialog"):
            yield Static("Discard your changes?")
            with DialogActions():
                yield Button("Keep editing", id="keep", variant="primary", compact=True)
                yield Button("Discard", id="discard", variant="error", compact=True)

    def on_mount(self) -> None:
        self.query_one("#keep", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "discard")


class EditorApp(App[EditResult]):
    """Single-buffer transactional editor; file persistence belongs to callers."""

    CSS = """
    #title { height: 1; padding: 0 1; background: $primary; }
    TextArea { height: 1fr; }
    #diagnostic { height: auto; max-height: 8; padding: 0 1; color: $error; }
    #find { height: 3; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f2", "accept", "Save & close", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("f3", "find", "Find", priority=True),
    ]

    def __init__(self, initial_text: str = "", *, title: str = "Text editor",
                 validator: Validator | None = None) -> None:
        super().__init__()
        self.title = title
        self.initial_text = initial_text
        self.newline = line_ending(initial_text)
        self.validator = validator
        self.failure: Exception | None = None

    def compose(self) -> ComposeResult:
        yield Static(self.title, id="title", markup=False)
        yield TextArea(self.initial_text.replace("\r\n", "\n"), id="buffer",
                       show_line_numbers=True, tab_behavior="indent")
        yield Input(placeholder="Find text; Enter finds next, Escape returns to editing", id="find")
        yield Static("", id="diagnostic", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#find", Input).display = False
        self.query_one(TextArea).focus()

    @property
    def candidate(self) -> str:
        """Restore the document's original uniform separator convention."""
        return self.query_one(TextArea).text.replace("\r\n", "\n").replace("\n", self.newline)

    def action_accept(self) -> None:
        if isinstance(self.screen, DiscardDialog):
            return
        candidate = self.candidate
        try:
            diagnostic = self.validator(candidate) if self.validator else None
        except Exception as error:  # noqa: BLE001 - propagate caller failures after App.run restores the terminal
            self.failure = error
            self.exit(EditResult("cancelled"))
            return
        if diagnostic is not None:
            self.query_one("#diagnostic", Static).update(diagnostic)
            self.query_one(TextArea).focus()
            return
        self.exit(EditResult("accepted", candidate))

    def action_cancel(self) -> None:
        if isinstance(self.screen, DiscardDialog):
            self.screen.dismiss(False)
            return
        find = self.query_one("#find", Input)
        if find.display:
            find.display = False
            self.query_one(TextArea).focus()
        elif self.candidate != self.initial_text:
            self.push_screen(DiscardDialog(), self._discard_answer)
        else:
            self.exit(EditResult("cancelled"))

    def _discard_answer(self, discard: bool | None) -> None:
        if discard:
            self.exit(EditResult("cancelled"))
        else:
            self.query_one(TextArea).focus()

    def action_find(self) -> None:
        if isinstance(self.screen, DiscardDialog):
            return
        find = self.query_one("#find", Input)
        find.display = True
        find.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not event.value:
            return
        area = self.query_one(TextArea)
        row, column = area.cursor_location
        start = sum(len(line) + 1 for line in area.text.split("\n")[:row]) + column
        index = area.text.find(event.value, start + 1)
        if index < 0:
            index = area.text.find(event.value)
        if index < 0:
            self.query_one("#diagnostic", Static).update("Text not found")
        else:
            row = area.text.count("\n", 0, index)
            column = index - area.text.rfind("\n", 0, index) - 1
            area.move_cursor((row, column), center=True)
            self.query_one("#diagnostic", Static).update("")
