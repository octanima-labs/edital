"""Multi-tab Textual adapter for the framework-independent file session."""

from collections.abc import Callable
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Button, Footer, Input, Static, Tab, Tabs, TextArea

from .app import DiscardDialog
from .documents import SessionFile
from .editor import ConfirmationRequired, Edital


class PathDialog(ModalScreen[str | None]):
    """Collect a destination/open path without changing document state."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "cancel", "Cancel")]

    def __init__(self, title: str) -> None:
        super().__init__()
        self.dialog_title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="path-dialog"):
            yield Static(self.dialog_title, markup=False)
            yield Input(placeholder="File path", id="path")
            yield Button("Continue", id="continue", variant="primary")
            yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        else:
            self._submit()

    def _submit(self) -> None:
        path = self.query_one(Input).value
        if path.strip():
            self.dismiss(path)

    def action_cancel(self) -> None:
        self.dismiss(None)


class RecoveryDialog(ModalScreen[str | None]):
    """Select which version to retain when disk changed since a snapshot."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "cancel", "Keep unresolved")]

    def __init__(self, document: SessionFile) -> None:
        super().__init__()
        self.document = document

    def compose(self) -> ComposeResult:
        with Vertical(id="recovery-dialog"):
            yield Static(f"Disk changed: {self.document.path}", markup=False)
            yield Static("Choose a version. No file is written by this choice.")
            yield Button("Use recovered text", id="recovered", variant="primary")
            yield Button("Use disk text", id="disk")
            yield Button("Keep recovery as separate draft", id="draft")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FileEditorApp(App[None]):
    """Retain a TextArea per document; delegate preservation to ``Edital``."""

    CSS = """
    Tabs { height: 3; }
    #documents { height: 1fr; }
    TextArea { height: 1fr; }
    #empty { padding: 2; }
    #diagnostic { height: auto; max-height: 5; color: $error; padding: 0 1; }
    #find { height: 3; }
    ModalScreen { align: center middle; background: $background 70%; }
    #path-dialog, #recovery-dialog, #discard-dialog {
        width: 65; height: auto; padding: 1 2; border: thick $primary;
    }
    ModalScreen Button { width: 100%; margin-top: 1; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+n", "new", "New", priority=True),
        Binding("ctrl+o", "open", "Open", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("ctrl+w", "close", "Close tab", priority=True),
        Binding("f2", "save_close", "Save & close", priority=True),
        Binding("f3", "save_exit", "Save all & exit", priority=True),
        Binding("f4", "find", "Find", priority=True),
        Binding("ctrl+pagedown", "next_tab", "Next tab", priority=True),
        Binding("ctrl+pageup", "previous_tab", "Previous tab", priority=True),
        Binding("escape", "cancel", "Exit", priority=True),
    ]

    def __init__(self, editor: Edital) -> None:
        super().__init__()
        self.editor = editor
        self.areas: dict[str, TextArea] = {}
        self._timer: Timer | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._reconciling = False

    def compose(self) -> ComposeResult:
        yield Tabs(id="tabs")
        with Vertical(id="documents"):
            yield Static("No documents. Ctrl+N creates a draft; Ctrl+O opens a file.", id="empty")
        yield Input(placeholder="Find; Enter finds next, Escape returns to editing", id="find")
        yield Static("", id="diagnostic", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one("#find", Input).display = False
        self.editor._on_exit = self.exit
        self._unsubscribe = self.editor.conf.subscribe(self._configuration_changed)
        await self.reconcile()
        self._schedule_timer()
        self.resolve_conflicts()

    def on_unmount(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
        self.editor._on_exit = None
        self.editor._confirm = None

    def _configuration_changed(self, key: str) -> None:
        if key == "auto_save":
            self._schedule_timer()

    def _schedule_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        interval = self.editor.conf.get("auto_save")
        if interval > 0:
            self._timer = self.set_interval(interval / 1000, self._autosave)

    def _autosave(self) -> None:
        self.sync_text()
        for document, error in self.editor.autosave():
            self.diagnostic(f"Autosave failed for {document.path}: {error}")
        self.update_labels()

    def diagnostic(self, message: str) -> None:
        self.screen_stack[0].query_one("#diagnostic", Static).update(message)

    def sync_text(self) -> None:
        for document in self.editor.files:
            area = self.areas.get(document.id)
            if area is not None:
                document.text = area.text.replace("\r\n", "\n").replace("\n", document.newline)

    def label(self, document: SessionFile) -> str:
        if document.path is None:
            name = document.draft_name
        else:
            duplicate = any(d is not document and d.path is not None and d.path.name == document.path.name
                            for d in self.editor.files)
            name = str(document.path) if duplicate else document.path.name
        return name + (" !" if document.conflict else " *" if document.modified else "")

    def update_labels(self) -> None:
        tabs = self.screen_stack[0].query_one("#tabs", Tabs)
        for document in self.editor.files:
            if document.id in self.areas:
                tab = tabs.get_tab(f"tab-{document.id}")
                label = self.label(document)
                if tab is not None and tab.label.plain != label:
                    tab.label = Content(label)

    async def reconcile(self) -> None:
        self._reconciling = True
        active = self.editor.session.active
        tabs = self.screen_stack[0].query_one("#tabs", Tabs)
        container = self.screen_stack[0].query_one("#documents", Vertical)
        identities = {d.id for d in self.editor.files}
        for identity in tuple(self.areas):
            if identity not in identities:
                await self.areas.pop(identity).remove()
                await tabs.remove_tab(f"tab-{identity}")
        for document in self.editor.files:
            if document.id not in self.areas:
                area = TextArea(document.text.replace("\r\n", "\n"), id=f"buffer-{document.id}",
                                show_line_numbers=True, tab_behavior="indent")
                self.areas[document.id] = area
                await container.mount(area)
                await tabs.add_tab(Tab(Content(self.label(document)), id=f"tab-{document.id}"))
        self.screen_stack[0].query_one("#empty").display = not self.editor.files
        self.editor.session.active = active
        self.update_labels()
        self.select_active()
        self._reconciling = False

    def select_active(self) -> None:
        active = self.editor.session.active
        for identity, area in self.areas.items():
            area.display = active is not None and identity == active.id
        if active is not None and active.id in self.areas:
            self.screen_stack[0].query_one("#tabs", Tabs).active = f"tab-{active.id}"
            self.areas[active.id].focus()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if self._reconciling or event.tab.id != event.tabs.active or not self.is_running:
            return
        active = next((d for d in self.editor.files if f"tab-{d.id}" == event.tab.id), None)
        if active is not None:
            self.editor.session.active = active
            self.select_active()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.sync_text()
        self.update_labels()

    def can_interact(self) -> bool:
        return not isinstance(self.screen, ModalScreen)

    async def _save_document(self, document: SessionFile) -> bool:
        if document.conflict and not await self._resolve_conflict(document):
            return False
        path = None
        if document.path is None:
            path = await self.push_screen_wait(PathDialog("Save As"))
            if path is None:
                return False
        self.sync_text()
        try:
            self.editor.save(document, path=path)
        except (OSError, ValueError) as error:
            self.diagnostic(str(error))
            return False
        self.update_labels()
        return True

    async def _resolve_conflict(self, document: SessionFile) -> bool:
        choice = await self.push_screen_wait(RecoveryDialog(document))
        if choice is None:
            return False
        try:
            self.editor.resolve_recovery(document, choice)  # type: ignore[arg-type]
        except (OSError, ValueError) as error:
            self.diagnostic(str(error))
            return False
        area = self.areas.get(document.id)
        if area is not None:
            area.load_text(document.text.replace("\r\n", "\n"))
        await self.reconcile()
        return True

    @work(group="commands")
    async def resolve_conflicts(self) -> None:
        for document in self.editor.files:
            if document.conflict and not await self._resolve_conflict(document):
                break

    @work(group="commands")
    async def action_new(self) -> None:
        if self.can_interact():
            self.editor.new()
            await self.reconcile()

    @work(group="commands")
    async def action_open(self) -> None:
        if not self.can_interact():
            return
        path = await self.push_screen_wait(PathDialog("Open file (missing paths become drafts)"))
        if path is not None:
            try:
                self.editor.open(path)
                await self.reconcile()
            except (OSError, ValueError) as error:
                self.diagnostic(str(error))

    @work(group="commands")
    async def action_save(self) -> None:
        document = self.editor.session.active
        if self.can_interact() and document is not None:
            await self._save_document(document)

    @work(group="commands")
    async def action_save_close(self) -> None:
        document = self.editor.session.active
        if self.can_interact() and document is not None and await self._save_document(document):
            self.editor.close(document)
            await self.reconcile()

    @work(group="commands")
    async def action_save_exit(self) -> None:
        if not self.can_interact():
            return
        for document in self.editor.files:
            if not await self._save_document(document):
                return
        await self._remove_documents(exiting=True)

    async def _remove_documents(self, *, exiting: bool) -> None:
        self.sync_text()
        document = self.editor.session.active
        try:
            if exiting:
                self.editor.exit()
            elif document is not None:
                self.editor.close(document)
        except ConfirmationRequired:
            discard = await self.push_screen_wait(DiscardDialog())
            if discard:
                self.editor._confirm = lambda: True
                try:
                    if exiting:
                        self.editor.exit()
                    elif document is not None:
                        self.editor.close(document)
                except (OSError, ValueError) as error:
                    self.diagnostic(str(error))
                finally:
                    self.editor._confirm = None
        except (OSError, ValueError) as error:
            self.diagnostic(str(error))
        if not self.editor.exited:
            await self.reconcile()

    @work(group="commands")
    async def action_close(self) -> None:
        if self.can_interact():
            await self._remove_documents(exiting=False)

    def action_cancel(self) -> None:
        if isinstance(self.screen, DiscardDialog):
            self.screen.dismiss(False)
        elif isinstance(self.screen, ModalScreen):
            self.screen.dismiss(None)
        elif self.query_one("#find", Input).display:
            self.query_one("#find", Input).display = False
            self.select_active()
        else:
            self.request_exit()

    @work(group="commands")
    async def request_exit(self) -> None:
        await self._remove_documents(exiting=True)

    def _switch(self, offset: int) -> None:
        if self.can_interact() and self.editor.files:
            documents = self.editor.files
            current = self.editor.session.active
            index = documents.index(current) if current is not None else 0
            self.editor.session.active = documents[(index + offset) % len(documents)]
            self.select_active()

    def action_next_tab(self) -> None:
        self._switch(1)

    def action_previous_tab(self) -> None:
        self._switch(-1)

    def action_find(self) -> None:
        if self.can_interact() and self.editor.session.active is not None:
            find = self.query_one("#find", Input)
            find.display = True
            find.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        document = self.editor.session.active
        if event.input.id != "find" or not event.value or document is None:
            return
        area = self.areas[document.id]
        row, column = area.cursor_location
        start = sum(len(line) + 1 for line in area.text.split("\n")[:row]) + column
        index = area.text.find(event.value, start + 1)
        if index < 0:
            index = area.text.find(event.value)
        if index < 0:
            self.diagnostic("Text not found")
        else:
            area.move_cursor((area.text.count("\n", 0, index), index - area.text.rfind("\n", 0, index) - 1),
                             center=True)
            self.diagnostic("")
