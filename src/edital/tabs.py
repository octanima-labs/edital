"""Close-aware tabs that retain Textual's navigation and scrolling."""

import sys
from itertools import pairwise

from rich.cells import cell_len
from textual import events
from textual.content import Content
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Tab, Tabs


def close_glyph() -> str:
    """Prefer a single-cell Unicode cross when the output encoding supports it."""
    try:
        encoding = getattr(sys.stdout, "encoding", None) or getattr(sys.__stdout__, "encoding", None)
        "⨯".encode(encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        return "X"
    return "⨯" if cell_len("⨯") == 1 else "X"


class DocumentTab(Tab):
    """A tab whose right-hand cross requests closing rather than activation."""

    class CloseRequested(Message):
        """Request removal of the document identified by the clicked tab."""

        def __init__(self, document_id: str) -> None:
            super().__init__()
            self.document_id = document_id

    def __init__(self, title: str, document_id: str) -> None:
        self.document_id = document_id
        self.close_icon = close_glyph()
        super().__init__(Content(f"{title}  {self.close_icon}"), id=f"tab-{document_id}")

    def set_title(self, title: str) -> None:
        """Refresh the literal title while retaining the close control."""
        label = f"{title}  {self.close_icon}"
        if self.label.plain != label:
            self.label = Content(label)

    @property
    def close_offset(self) -> int:
        """The close glyph's widget-local cell column, including left padding."""
        return self.styles.padding.left + cell_len(self.label.plain) - 1

    async def _on_click(self, event: events.Click | None = None) -> None:
        if event is None:
            return
        event.prevent_default()
        event.stop()
        if event.button != 1:
            return
        offset = event.screen_offset - self.region.offset
        if offset.x == self.close_offset and offset.y == self.styles.padding.top:
            self.post_message(self.CloseRequested(self.document_id))
        else:
            self.post_message(self.Clicked(self))


class DocumentTabs(Tabs):
    """Keep Textual's tab layout aligned with authoritative session order."""

    def reorder(self, identities: list[str]) -> None:
        """Move headers in place, retaining buffers and active tab identity."""
        headers = [self.get_tab(f"tab-{identity}") for identity in identities]
        for previous, current in pairwise(headers):
            if current is not None and previous is not None and isinstance(current.parent, Widget):
                current.parent.move_child(current, after=previous)
        self.call_after_refresh(self._highlight_active, animate=False)
