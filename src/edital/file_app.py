"""Multi-tab Textual adapter for the framework-independent file session."""

from collections.abc import Callable
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Button, Footer, Input, Static, Tabs, TextArea

from .app import DialogActions, DiscardDialog
from .controls import HelpDialog, bindings, cheatsheet
from .document_picker import DocumentPicker
from .documents import SessionFile
from .editor import ConfirmationRequired, Edital
from .search import SearchPanel
from .tabs import DocumentTab, DocumentTabs


class PathDialog(ModalScreen[str | None]):
    """Collect a destination/open path without changing document state."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    #path-dialog {
        width: 55; max-width: 100%; height: auto; max-height: 100%;
        overflow-y: auto; padding: 1 2; border: thick $primary;
    }
    """

    def __init__(self, title: str, submit: Callable[[str], None] | None = None) -> None:
        super().__init__()
        self.dialog_title = title
        self.submit = submit

    def compose(self) -> ComposeResult:
        with Vertical(id="path-dialog"):
            yield Static(self.dialog_title, markup=False)
            yield Input(placeholder="File path", id="path")
            yield Static("", id="path-error", markup=False)
            with DialogActions():
                yield Button("Continue", id="continue", variant="primary", compact=True)
                yield Button("Cancel", id="cancel", compact=True)

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
            if self.submit is not None:
                try:
                    self.submit(path)
                except (OSError, ValueError) as error:
                    self.query_one("#path-error", Static).update(str(error))
                    self.query_one(Input).focus()
                    return
            self.dismiss(path)

    def action_cancel(self) -> None:
        self.dismiss(None)


class RecoveryDialog(ModalScreen[str | None]):
    """Select which version to retain when disk changed since a snapshot."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "cancel", "Keep unresolved")]

    def __init__(self, document: SessionFile, *, competing: bool = False) -> None:
        super().__init__()
        self.document = document
        self.competing = competing

    def compose(self) -> ComposeResult:
        with Vertical(id="recovery-dialog"):
            path = self.document.path
            heading = ("Destination is missing" if self.document.disk_text is None
                       else "Destination has another unsaved document" if self.competing
                       else "Destination changed since caching")
            yield Static(f"{heading}: {path}", markup=False)
            yield Static("Resolve cached changes. No destination file is written by this choice.")
            yield Button("Restore cached version", id="recovered", variant="primary")
            yield Static("Keep cached text in this tab for its original destination; save later.")
            yield Button("Discard cached version", id="disk")
            yield Static("Remove the cached copy and use the destination version."
                         if self.document.disk_text is not None else
                         "Remove the cached copy and leave an empty named draft.")
            yield Button("Keep cached version as separate draft", id="draft")
            yield Static("Keep cached text in an unnamed draft; retain the destination tab when available.")
            yield Static("Escape leaves this conflict unresolved.")

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
    #path-error { height: auto; color: $error; }
    TextArea:focus, Input:focus { border: tall $edital-focus; }
    SearchPanel Input:focus { border: none !important; }
    Button:focus { border: tall $edital-focus; }
    SearchPanel Button:focus { border: none !important; }
    DialogActions Button.-textual-compact:focus {
        border-top: none !important;
        border-bottom: none !important;
        border-left: solid $edital-focus !important;
        border-right: solid $edital-focus !important;
    }
    Tabs .underline--bar { color: $edital-focus; }
    Tabs:focus Tab.-active { color: $foreground; background: transparent; }
    Tab.state-draft, Tab.state-draft:hover { color: $edital-draft 50%; }
    Tab.state-conflict, Tab.state-conflict:hover { color: $edital-conflict 50%; }
    Tab.state-draft.-active, Tabs:focus Tab.state-draft.-active { color: $edital-draft; }
    Tab.state-conflict.-active, Tabs:focus Tab.state-conflict.-active { color: $edital-conflict; }
    ModalScreen { align: center middle; background: $background 70%; }
    #recovery-dialog {
        width: 65; max-width: 100%; height: auto; max-height: 100%;
        overflow-y: auto; padding: 1 2; border: thick $primary;
    }
    #recovery-dialog Button { width: 100%; margin-top: 1; }
    """
    BINDINGS: ClassVar[list[BindingType]] = bindings("standalone")

    def __init__(self, editor: Edital) -> None:
        self.editor = editor
        super().__init__()
        self.areas: dict[str, TextArea] = {}
        self._timer: Timer | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._reconciling = False

    def get_css_variables(self) -> dict[str, str]:
        variables = super().get_css_variables()
        variables.update({
            "edital-focus": self.editor.conf.get("focus_color"),
            "edital-draft": self.editor.conf.get("draft_color") or variables["foreground"],
            "edital-conflict": self.editor.conf.get("conflict_color") or variables["foreground"],
        })
        return variables

    def compose(self) -> ComposeResult:
        yield DocumentTabs(id="tabs")
        with Vertical(id="documents"):
            yield Static("No documents. Ctrl+N creates a draft; Ctrl+O opens a file.", id="empty")
        yield SearchPanel()
        yield Static("", id="diagnostic", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
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
        elif key in ("focus_color", "draft_color", "conflict_color"):
            self.refresh_css(animate=False)
            self.update_labels()

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
        picker = self.document_picker
        if picker is not None:
            picker.report(message)

    @property
    def document_picker(self) -> DocumentPicker | None:
        return next((screen for screen in self.screen_stack if isinstance(screen, DocumentPicker)), None)

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
        markers = (["▲"] if document.conflict else []) + (["⏺"] if document.modified else [])
        return " ".join([*markers, name])

    def update_labels(self) -> None:
        tabs = self.screen_stack[0].query_one("#tabs", Tabs)
        for document in self.editor.files:
            if document.id in self.areas:
                tab = tabs.get_tab(f"tab-{document.id}")
                if isinstance(tab, DocumentTab):
                    tab.set_title(self.label(document))
                    state = self.document_state(document)
                    tab.set_class(state == "conflict", "state-conflict")
                    tab.set_class(state == "draft", "state-draft")
        picker = self.document_picker
        if picker is not None and picker.is_mounted:
            picker.refresh_titles()

    def document_state(self, document: SessionFile) -> str | None:
        """Share state-color precedence between tab headers and picker rows."""
        if document.conflict and self.editor.conf.get("conflict_color") is not None:
            return "conflict"
        if not document.autosave_eligible and self.editor.conf.get("draft_color") is not None:
            return "draft"
        return None

    async def reconcile(self, *, focus: bool = True) -> None:
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
                await tabs.add_tab(DocumentTab(self.label(document), document.id))
        self.screen_stack[0].query_one("#empty").display = not self.editor.files
        if isinstance(tabs, DocumentTabs):
            tabs.reorder([d.id for d in self.editor.files])
        self.editor.session.active = active
        self.update_labels()
        self.select_active(focus=focus)
        self._reconciling = False

    def select_active(self, *, focus: bool = True) -> None:
        active = self.editor.session.active
        for identity, area in self.areas.items():
            area.display = active is not None and identity == active.id
        self.screen_stack[0].query_one(SearchPanel).attach(
            self.areas.get(active.id) if active is not None else None
        )
        if active is not None and active.id in self.areas:
            tabs = self.screen_stack[0].query_one("#tabs", Tabs)
            tabs.active = f"tab-{active.id}"
            if tabs.active_tab is not None:
                self.call_after_refresh(tabs.active_tab.scroll_visible, animate=False, force=True)
            if focus and self.can_interact():
                self.areas[active.id].focus()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if (self._reconciling or event.tab.id != event.tabs.active or not self.is_running
                or not self.can_interact()):
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
        if document.path is None:
            def save(path: str) -> None:
                self.sync_text()
                self.editor.save(document, path=path)

            path = await self.push_screen_wait(PathDialog("Save As", submit=save))
            if path is None:
                return False
        else:
            self.sync_text()
            try:
                self.editor.save(document)
            except (OSError, ValueError) as error:
                self.diagnostic(str(error))
                return False
        self.update_labels()
        return True

    async def _resolve_conflict(self, document: SessionFile) -> bool:
        competing = any(d is not document and d.path == document.path for d in self.editor.files)
        choice = await self.push_screen_wait(RecoveryDialog(document, competing=competing))
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

    async def _remove_documents(self, *, exiting: bool, document: SessionFile | None = None,
                                focus: bool = True) -> None:
        self.sync_text()
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
            await self.reconcile(focus=focus)

    @work(group="commands")
    async def action_close(self) -> None:
        if isinstance(self.screen, DocumentPicker):
            self.screen.request_close(self.screen.highlighted_id)
        elif self.can_interact():
            await self._remove_documents(exiting=False, document=self.editor.session.active)

    @work(group="commands")
    async def on_document_tab_close_requested(self, event: DocumentTab.CloseRequested) -> None:
        if self.can_interact():
            document = next((d for d in self.editor.files if d.id == event.document_id), None)
            if document is not None:
                await self._remove_documents(exiting=False, document=document)

    def action_cancel(self) -> None:
        if isinstance(self.screen, DiscardDialog):
            self.screen.dismiss(False)
        elif isinstance(self.screen, DocumentPicker) and self.screen.busy:
            return
        elif isinstance(self.screen, ModalScreen):
            self.screen.dismiss(None)
        elif self.query_one(SearchPanel).display:
            self.query_one(SearchPanel).close()
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

    async def _move(self, offset: int) -> None:
        if isinstance(self.screen, DocumentPicker):
            picker = self.screen
            if picker.busy:
                return
            document = next((d for d in self.editor.files if d.id == picker.highlighted_id), None)
            if document is None:
                return
            target = self.editor.files.index(document) + offset
            if 0 <= target < len(self.editor.files):
                picker.busy = True
                try:
                    self.editor.session.move(document, target)
                    await self.reconcile(focus=False)
                    await picker.reconcile_rows()
                finally:
                    picker.busy = False
            return
        current = self.editor.session.active
        if not self.can_interact() or current is None:
            return
        target = self.editor.files.index(current) + offset
        if 0 <= target < len(self.editor.files):
            self.editor.session.move(current, target)
            await self.reconcile()

    @work(group="commands")
    async def action_move_left(self) -> None:
        await self._move(-1)

    @work(group="commands")
    async def action_move_right(self) -> None:
        await self._move(1)

    def action_documents(self) -> None:
        if not self.can_interact() or not self.editor.files:
            return
        self.sync_text()
        origin = self.focused

        def chosen(identity: str | None) -> None:
            document = next((d for d in self.editor.files if d.id == identity), None)
            if document is not None:
                self.editor.session.active = document
                self.select_active()
            elif not self.editor.files:
                self.screen_stack[0].query_one(SearchPanel).close()
                self.screen_stack[0].set_focus(None)
            elif origin is not None and origin.is_mounted and origin.display:
                origin.focus()
            else:
                self.select_active()

        self.push_screen(DocumentPicker(self.editor.session, self.label, self.document_state), chosen)

    @work(group="commands")
    async def on_document_picker_close_requested(self, event: DocumentPicker.CloseRequested) -> None:
        event.stop()
        picker = event.picker
        if self.screen is not picker or picker.busy:
            return
        document = next((d for d in self.editor.files if d.id == event.document_id), None)
        if document is None:
            return
        picker.busy = True
        picker.report("")
        try:
            await self._remove_documents(exiting=False, document=document, focus=False)
            await picker.reconcile_rows()
        finally:
            picker.busy = False

    def action_find(self) -> None:
        if self.can_interact() and self.editor.session.active is not None:
            self.query_one(SearchPanel).open(self.areas[self.editor.session.active.id], replace=False)

    def action_replace(self) -> None:
        if self.can_interact() and self.editor.session.active is not None:
            self.query_one(SearchPanel).open(self.areas[self.editor.session.active.id], replace=True)

    def action_help(self) -> None:
        if isinstance(self.screen, HelpDialog):
            self.screen.dismiss(None)
        else:
            active = self.editor.session.active
            area = self.areas.get(active.id) if active is not None else None
            self.push_screen(HelpDialog(cheatsheet("standalone", area, type(self.screen).__name__, self._bindings)))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if ((isinstance(self.screen, HelpDialog) or self.document_picker is not None)
                and action in ("quit", "command_palette")):
            return False
        return super().check_action(action, parameters)
