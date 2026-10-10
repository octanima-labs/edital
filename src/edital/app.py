"""Textual implementation of Edital's standalone text-session contract."""

from typing import ClassVar

from textual import events
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static, TextArea

from .controls import EmbeddedTextArea, HelpDialog, bindings, cheatsheet
from .search import SearchPanel
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
    """
    BINDINGS: ClassVar[list[BindingType]] = bindings("embedded")

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
        yield EmbeddedTextArea(self.initial_text.replace("\r\n", "\n"), id="buffer",
                        show_line_numbers=True, tab_behavior="indent")
        yield SearchPanel()
        yield Static("", id="diagnostic", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(TextArea).focus()

    @property
    def candidate(self) -> str:
        """Restore the document's original uniform separator convention."""
        return self.query_one(TextArea).text.replace("\r\n", "\n").replace("\n", self.newline)

    def action_accept(self) -> None:
        if isinstance(self.screen, ModalScreen):
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
        if isinstance(self.screen, HelpDialog):
            self.screen.dismiss(None)
            return
        if isinstance(self.screen, DiscardDialog):
            self.screen.dismiss(False)
            return
        search = self.query_one(SearchPanel)
        if search.display:
            search.close()

    async def action_quit(self) -> None:
        """Explicitly cancel, retaining transactional discard confirmation."""
        if isinstance(self.screen, ModalScreen):
            return
        if self.candidate != self.initial_text:
            origin = self.focused

            def discard_answer(discard: bool | None) -> None:
                if discard:
                    self.exit(EditResult("cancelled"))
                elif origin is not None and origin.is_mounted:
                    origin.focus()
                else:
                    self.query_one(TextArea).focus()

            self.push_screen(DiscardDialog(), discard_answer)
        else:
            self.exit(EditResult("cancelled"))

    def action_find(self) -> None:
        if isinstance(self.screen, ModalScreen):
            return
        self.query_one(SearchPanel).open(self.query_one(TextArea), replace=False)

    def action_replace(self) -> None:
        if not isinstance(self.screen, ModalScreen):
            self.query_one(SearchPanel).open(self.query_one(TextArea), replace=True)

    def action_help(self) -> None:
        if isinstance(self.screen, HelpDialog):
            self.screen.dismiss(None)
        else:
            area = self.screen_stack[0].query_one(TextArea)
            self.push_screen(HelpDialog(cheatsheet("embedded", area, type(self.screen).__name__, self._bindings)))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "quit" and isinstance(self.screen, ModalScreen):
            return False
        if isinstance(self.screen, HelpDialog) and action in ("quit", "command_palette"):
            return False
        return super().check_action(action, parameters)
