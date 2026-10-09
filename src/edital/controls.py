"""Canonical UI controls and context-preserving keyboard help."""

from dataclasses import dataclass
from typing import ClassVar, Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingsMap, BindingType
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

Mode = Literal["standalone", "embedded"]


@dataclass(frozen=True)
class Control:
    """One semantic control, with mode-specific dispatch and discovery."""

    key: str
    standalone: str
    embedded: str | None
    description: str
    group: str
    show: bool = False


CONTROLS = (
    Control("f1", "help", "help", "Help", "Files and session", True),
    Control("f2", "save_close", "accept", "Save / accept & close", "Files and session", True),
    Control("f3", "save_exit", "accept", "Save / accept all & finish", "Files and session"),
    Control("f4", "find", "find", "Find", "Find and replace", True),
    Control("f5", "replace", "replace", "Replace", "Find and replace", True),
    Control("escape", "cancel", "cancel", "Exit / cancel", "Files and session", True),
    Control("ctrl+n", "new", None, "New draft", "Files and session"),
    Control("ctrl+o", "open", None, "Open file", "Files and session"),
    Control("ctrl+s", "save", None, "Save without closing", "Files and session"),
    Control("ctrl+w", "close", None, "Close tab without caching", "Tabs"),
    Control("ctrl+pageup", "previous_tab", None, "Previous tab", "Tabs"),
    Control("ctrl+pagedown", "next_tab", None, "Next tab", "Tabs"),
    Control("ctrl+shift+pageup", "move_left", None, "Move tab left", "Tabs"),
    Control("ctrl+shift+pagedown", "move_right", None, "Move tab right", "Tabs"),
)


def bindings(mode: Mode) -> list[BindingType]:
    """Build app bindings; embedded reservations belong to its document widget."""
    result: list[BindingType] = []
    for control in CONTROLS:
        action = control.standalone if mode == "standalone" else control.embedded
        if action is not None:
            description = control.description
            if control.key == "f2":
                description = "Save & close" if mode == "standalone" else "Accept & close"
            elif control.key == "escape":
                description = "Exit" if mode == "standalone" else "Cancel"
            result.append(Binding(control.key, action, description, show=control.show, priority=True))
    return result


class EmbeddedTextArea(TextArea):
    """Reserve file-only controls without changing editing in dialog inputs."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding(c.key, "reserved", "Unavailable", show=False)
                for c in CONTROLS if c.embedded is None]

    def action_reserved(self) -> None:
        """File and tab actions have no meaning in a transactional buffer."""


def cheatsheet(mode: Mode, area: TextArea | None, context: str,
               app_bindings: BindingsMap) -> str:
    """Describe actual document bindings, excluding overridden aliases."""
    groups: dict[str, list[str]] = {}
    reserved = {c.key for c in CONTROLS}
    for control in CONTROLS:
        description = control.description
        if mode == "embedded":
            if control.embedded is None:
                description += " — unavailable in embedded editing"
            elif control.key in ("f2", "f3"):
                description = "Validate, accept text, and close (no file write)"
            elif control.key == "escape":
                description = "Dismiss interaction first; otherwise cancel"
        elif control.key == "escape":
            description = "Dismiss interaction first; otherwise exit using cache settings"
        groups.setdefault(control.group, []).append(f"{control.key}: {description}")
    # Include inherited controls, even in an empty standalone workspace.
    document_bindings = area._bindings if area is not None else BindingsMap(TextArea.BINDINGS)
    priority_keys = {key for key, alternatives in app_bindings.key_to_bindings.items()
                     if any(b.priority for b in alternatives)}
    for key, alternatives in document_bindings.key_to_bindings.items():
        if key in reserved or key in priority_keys:
            continue
        binding = alternatives[0]
        action = binding.action
        group = ("Clipboard and undo" if action in ("copy", "cut", "paste", "undo", "redo")
                 else "Navigation and selection")
        groups.setdefault(group, []).append(f"{key}: {binding.description}")
    for key, alternatives in app_bindings.key_to_bindings.items():
        if key in reserved:
            continue
        binding = alternatives[0]
        if binding.system or (key in document_bindings.key_to_bindings and not binding.priority):
            continue
        groups.setdefault("Application controls", []).append(f"{key}: {binding.description}")
    groups["Current interaction"] = [
        context,
        "Search: Enter finds next; Tab moves among inputs and actions.",
        r"Regex: toggle OFF/ON beside Find; ON uses Python patterns and replacement captures \g<1> or \g<name>.",
        "Dialogs: Tab moves focus; Enter activates; Escape dismisses.",
        "Help: Up/Down or PageUp/PageDown scroll; Escape or F1 closes help.",
    ]
    return "Keyboard cheatsheet\n\n" + "\n\n".join(
        heading + "\n" + "\n".join(lines) for heading, lines in groups.items()
    )


class HelpDialog(ModalScreen[None]):
    """Scrollable help layered above, rather than replacing, an interaction."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "close", "Close help"), ("f1", "close", "Close help")]
    DEFAULT_CSS = """
    HelpDialog { align: center middle; background: $background 70%; }
    #cheatsheet {
        width: 80; max-width: 100%; height: 85%; max-height: 100%;
        border: thick $primary; padding: 1 2;
    }
    #help-title { color: $accent; text-style: bold; text-align: center; }
    #help-hint { color: $text-muted; text-align: center; margin-bottom: 1; }
    .help-heading {
        color: $accent; text-style: bold; border-bottom: solid $primary;
        margin-top: 1; margin-bottom: 1;
    }
    .help-body { padding: 0 1; }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="cheatsheet", can_focus=True):
            title, *sections = self.text.split("\n\n")
            yield Static(title, markup=False, id="help-title")
            yield Static("Scroll: ↑ ↓ / PageUp PageDown  ·  Close: Esc / F1", markup=False, id="help-hint")
            for section in sections:
                heading, _, body = section.partition("\n")
                yield Static(heading, markup=False, classes="help-heading")
                highlighted = Text()
                for index, line in enumerate(body.splitlines()):
                    if index:
                        highlighted.append("\n")
                    key, separator, description = line.partition(": ")
                    if separator:
                        highlighted.append(key, style="bold yellow")
                        highlighted.append("  —  ", style="dim")
                        highlighted.append(description)
                    else:
                        highlighted.append(line)
                yield Static(highlighted, classes="help-body")

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()

    def action_close(self) -> None:
        self.dismiss(None)
