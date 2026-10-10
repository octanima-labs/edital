"""A tentative, identity-keyed overview of the standalone document session."""

from collections.abc import Callable
from typing import ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Static

from .documents import EditalSession, SessionFile
from .tabs import close_glyph


class DocumentRow(Horizontal):
    """A single-line title with an independent, fixed-width close target."""

    class Chosen(Message):
        def __init__(self, document_id: str, *, close: bool) -> None:
            super().__init__()
            self.document_id = document_id
            self.close = close

    def __init__(self, document_id: str) -> None:
        super().__init__(id=f"document-row-{document_id}")
        self.document_id = document_id

    def compose(self) -> ComposeResult:
        yield Static("", classes="picker-name", markup=False)
        yield Static(close_glyph(), classes="picker-close", markup=False)

    def update_title(self, title: str, state: str | None, highlighted: bool) -> None:
        self.query_one(".picker-name", Static).update(Text(title, no_wrap=True, overflow="ellipsis"))
        self.set_class(state == "conflict", "state-conflict")
        self.set_class(state == "draft", "state-draft")
        self.set_class(highlighted, "highlighted")

    def on_click(self, event: events.Click) -> None:
        event.stop()
        event.prevent_default()
        if event.button == 1:
            close = self.query_one(".picker-close").region.contains(event.screen_x, event.screen_y)
            self.post_message(self.Chosen(self.document_id, close=close))


class DocumentPicker(ModalScreen[str | None]):
    """Browse documents without activating them until explicitly chosen."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "navigate(-1)", "Previous document", priority=True),
        Binding("down", "navigate(1)", "Next document", priority=True),
        Binding("pageup", "page(-1)", "Previous page", priority=True),
        Binding("pagedown", "page(1)", "Next page", priority=True),
        Binding("home", "edge(False)", "First document", priority=True),
        Binding("end", "edge(True)", "Last document", priority=True),
        Binding("enter", "choose", "Select document", priority=True),
    ]

    DEFAULT_CSS = """
    #document-picker {
        width: 80; max-width: 100%; height: 75%; min-height: 8; max-height: 100%;
        padding: 0 1; border: tall $edital-focus;
    }
    #picker-title { height: 1; text-style: bold; color: $accent; }
    #picker-list { height: 1fr; min-height: 1; padding: 0; }
    #picker-hints, #picker-error { height: auto; }
    #picker-error { color: $error; }
    DocumentRow { height: 1; padding: 0 1; border: none; }
    DocumentRow .picker-name { height: 1; width: 1fr; min-width: 1; }
    DocumentRow .picker-close { height: 1; width: 3; color: $text-muted; text-align: center; }
    DocumentRow .picker-close:hover { color: $error; background: $surface; }
    DocumentRow:hover { background: $surface; }
    DocumentRow.highlighted { background: $edital-focus 25%; text-style: bold; }
    DocumentRow.state-draft { color: $edital-draft 50%; }
    DocumentRow.state-conflict { color: $edital-conflict 50%; }
    DocumentRow.state-draft.highlighted { color: $edital-draft; }
    DocumentRow.state-conflict.highlighted { color: $edital-conflict; }
    """

    class CloseRequested(Message):
        def __init__(self, picker: "DocumentPicker", document_id: str) -> None:
            super().__init__()
            self.picker = picker
            self.document_id = document_id

    def __init__(self, session: EditalSession, label: Callable[[SessionFile], str],
                 state: Callable[[SessionFile], str | None]) -> None:
        super().__init__()
        self.session = session
        self.label = label
        self.state = state
        self.highlighted_id = session.active.id if session.active is not None else None
        self.rows: dict[str, DocumentRow] = {}
        self.order = [document.id for document in session.files]
        self.busy = False

    def compose(self) -> ComposeResult:
        with Vertical(id="document-picker"):
            yield Static("Open documents", id="picker-title")
            with VerticalScroll(id="picker-list", can_focus=True):
                for identity in self.order:
                    row = self.rows[identity] = DocumentRow(identity)
                    yield row
            yield Static("", id="picker-error", markup=False)
            yield Static("↑↓ Browse · Enter Select · Esc Close\n"
                         "Ctrl+Shift+PgUp/PgDn Reorder · Ctrl+W / ⨯ Close tab",
                         id="picker-hints", markup=False)

    def on_mount(self) -> None:
        self.query_one("#picker-list").focus()
        self.refresh_titles()
        self.call_after_refresh(self.keep_highlight_visible)

    def refresh_titles(self) -> None:
        """Refresh presentation in place, retaining highlight and scroll context."""
        for document in self.session.files:
            row = self.rows.get(document.id)
            if row is not None and row.is_mounted:
                row.update_title(self.label(document), self.state(document),
                                 document.id == self.highlighted_id)

    def keep_highlight_visible(self) -> None:
        row = self.rows.get(self.highlighted_id or "")
        if row is not None:
            row.scroll_visible(animate=False, force=True)

    async def reconcile_rows(self) -> None:
        """Apply membership/order changes without replacing surviving rows."""
        old_index = self.order.index(self.highlighted_id) if self.highlighted_id in self.order else 0
        self.order = [document.id for document in self.session.files]
        if not self.order:
            self.dismiss(None)
            return
        if self.highlighted_id not in self.order:
            self.highlighted_id = self.order[min(old_index, len(self.order) - 1)]
        container = self.query_one("#picker-list", VerticalScroll)
        for identity in tuple(self.rows):
            if identity not in self.order:
                await self.rows.pop(identity).remove()
        for identity in self.order:
            if identity not in self.rows:
                row = self.rows[identity] = DocumentRow(identity)
                await container.mount(row)
        for index, identity in enumerate(self.order):
            container.move_child(self.rows[identity], before=index)
        self.refresh_titles()
        self.call_after_refresh(self.keep_highlight_visible)

    def action_navigate(self, step: int) -> None:
        if self.busy or not self.order:
            return
        index = self.order.index(self.highlighted_id) if self.highlighted_id in self.order else 0
        self.highlighted_id = self.order[max(0, min(index + step, len(self.order) - 1))]
        self.refresh_titles()
        self.keep_highlight_visible()

    def action_page(self, direction: int) -> None:
        self.action_navigate(direction * max(1, self.query_one("#picker-list").content_region.height))

    def action_edge(self, last: bool) -> None:
        self.action_navigate(len(self.order) if last else -len(self.order))

    def action_choose(self) -> None:
        if not self.busy and self.highlighted_id in self.order:
            self.dismiss(self.highlighted_id)

    def on_document_row_chosen(self, event: DocumentRow.Chosen) -> None:
        event.stop()
        if self.busy or self.app.screen is not self or event.document_id not in self.order:
            return
        if event.close:
            self.request_close(event.document_id)
        else:
            self.dismiss(event.document_id)

    def request_close(self, document_id: str | None) -> None:
        """Share keyboard and mouse closing with topmost/busy guards."""
        if (document_id is not None and not self.busy and self.app.screen is self
                and document_id in self.order):
            self.post_message(self.CloseRequested(self, document_id))

    def report(self, message: str) -> None:
        self.query_one("#picker-error", Static).update(message)

    def on_resize(self) -> None:
        self.call_after_refresh(self.keep_highlight_visible)
