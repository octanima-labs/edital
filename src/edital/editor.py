"""Public file-editor facade; transactional embedded editing lives separately."""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from .configuration import EditalConf, storage_paths
from .documents import Document, EditalSession, SessionFile
from .persistence import read_text
from .recovery import CacheFile, RecoveryStore
from .session import line_ending


class ConfirmationRequired(RuntimeError):
    """A headless destructive operation requires interactive discard confirmation."""


class Edital:
    """Prepare file documents and launch a blocking multi-tab editor with ``run``.

    Keyword settings override user YAML. Opening and saving work without a TUI.
    ``auto_restore=True`` restores snapshots at ``run``, not during preparation.
    ``close`` removes one document; ``exit`` requests whole-editor termination.
    Files are UTF-8 with uniform LF/CRLF. Recovery covers orderly exit, not crashes.

    Args:
        **configuration_overrides: Validated instance settings: ``auto_save``
            (nonnegative milliseconds), ``cache``, ``prompt``, ``auto_restore``
            (booleans), and ``focus_color``, ``draft_color``, ``conflict_color``
            (hexadecimal colors). The two state colors also accept ``None``.

    Raises:
        ValueError: If user YAML or an effective setting is invalid.
        OSError: If the user configuration cannot be initialized or read.

    Notes:
        Construction creates a missing user configuration file and its parent
        directory, but does not import Textual, restore snapshots, or launch a UI.

    Examples:
        >>> editor = Edital(auto_save=0)
        >>> draft = editor.new()
        >>> draft.text = "Notes\\n"
        >>> editor.save(draft, path="notes.txt")
    """

    def __init__(self, **configuration_overrides: Any) -> None:
        self.conf = EditalConf(**configuration_overrides)
        self.session = EditalSession()
        _, self.cache_dir = storage_paths()
        self._recovery = RecoveryStore(self.cache_dir)
        self._confirm: Callable[[], bool] | None = None
        self._on_exit: Callable[[], None] | None = None
        self.exited = False

    @property
    def files(self) -> tuple[SessionFile, ...]:
        """Read-only ordered view of documents in the current session."""
        return self.session.files

    @property
    def cache(self) -> tuple[CacheFile, ...]:
        """Available persisted recovery entries; reading does not restore them."""
        return self._recovery.entries()

    def open(self, *paths: str | Path) -> tuple[SessionFile, ...]:
        """Load existing files or prepare named drafts without launching a UI.

        Args:
            *paths: Destinations, expanded and resolved against the working
                directory. Existing filesystem aliases select the same document.

        Returns:
            Handles in argument order, with the last selected as active. Reopened
            paths return existing handles; missing paths do not create files.

        Raises:
            OSError: If an existing file cannot be read.
            UnicodeError: If file content is not valid UTF-8.
            ValueError: If line endings are mixed or contain bare CR separators.

        Notes:
            Opening is sequential; a later failure leaves earlier documents open.
        """
        return self.session.open(*paths)

    def new(self) -> SessionFile:
        """Prepare one unnamed draft without creating a destination."""
        return self.session.new()

    def save(self, document: Document, *, path: str | Path | None = None) -> None:
        """Write current text and remove its associated recovery snapshot.

        Args:
            document: Open handle or destination path identifying a document.
            path: Optional new destination; required for an unnamed draft.
                An existing destination's contents are replaced.

        Raises:
            ValueError: If the document is not open, has an unresolved conflict,
                lacks a destination, targets another open document, or contains
                unsupported line endings.
            OSError: If writing the file or removing its snapshot fails.
            UnicodeError: If text cannot be encoded as UTF-8.

        Notes:
            A successful write updates the destination, saved baseline, and
            autosave eligibility before snapshot removal. A snapshot-removal
            failure therefore does not undo the file write.
        """
        current = self.session.resolve(document)
        self.session.save(current, path=path)
        if current.recovery_id is not None:
            self._recovery.remove(current.recovery_id)
            current.recovery_id = None

    def save_all(self) -> None:
        """Save sequentially; missing draft destinations/errors stop the operation."""
        for document in self.files:
            self.save(document)

    def _check_discard(self, documents: tuple[SessionFile, ...], cache: bool) -> None:
        if (not cache and self.conf.get("prompt") and any(d.modified or d.conflict for d in documents)
                and (self._confirm is None or not self._confirm())):
            raise ConfirmationRequired("Discard confirmation required; documents remain open")

    def _preserve(self, document: SessionFile, cache: bool) -> None:
        if cache and document.unsaved:
            self._recovery.snapshot(document)
        elif document.recovery_id is not None:
            self._recovery.remove(document.recovery_id)
            document.recovery_id = None

    def close(self, document: Document, *, cache: bool = False) -> None:
        """Remove one document; explicit caching overrides instance configuration.

        Without caching, dirty headless removal raises ``ConfirmationRequired``
        when prompts are enabled. Set ``prompt=False`` for deliberate discard.
        Closing the last document does not exit the application.

        Args:
            document: Open handle or destination path.
            cache: Preserve unsaved content in recovery before detaching it.
                Defaults to false regardless of the configured exit policy.

        Raises:
            ConfirmationRequired: If uncached removal requires confirmation.
            ValueError: If the document is not open.
            OSError: If preserving or removing its snapshot fails.
        """
        current = self.session.resolve(document)
        self._check_discard((current,), cache)
        self._preserve(current, cache)
        self.session.remove(current)

    def exit(self, *, cache: bool | None = None) -> None:
        """Preserve or discard all documents, then request editor termination.

        Args:
            cache: Whether to preserve unsaved content. ``None`` uses the
                instance's configured caching policy.

        Raises:
            ConfirmationRequired: If uncached discard requires confirmation.
            OSError: If recovery persistence fails; documents remain attached.

        Notes:
            Snapshots are processed before any documents are detached. A later
            failure can leave earlier snapshot changes persisted. Successful
            exit empties the session and sets ``exited`` to true; it does not
            revert content already written by explicit save or autosave.
        """
        enabled = self.conf.get("cache") if cache is None else cache
        documents = self.files
        self._check_discard(documents, enabled)
        # Preserve everything before detaching anything; failure keeps the session.
        for document in documents:
            self._preserve(document, enabled)
        for document in documents:
            self.session.remove(document)
        self.exited = True
        if self._on_exit is not None:
            self._on_exit()

    def restore(self) -> tuple[SessionFile, ...]:
        """Restore snapshots without consuming them or overwriting destinations.

        Conflicting documents remain blocked until ``resolve_recovery`` is called
        or the TUI collects a recovery choice. Repeated restoration, including
        automatic restoration at ``run``, is idempotent.

        Returns:
            Restored handles in snapshot order, including handles already
            associated with those snapshots.

        Raises:
            ValueError: If a snapshot or destination has invalid content.
            OSError: If reading recovery entries or destination files fails.
            UnicodeError: If destination content is not valid UTF-8.

        Notes:
            Restoration is sequential, so earlier restored documents remain
            if a later entry fails. Inspect each handle's ``conflict`` before
            saving; automatic saving skips unresolved conflicts.
        """
        result = []
        for entry in self.cache:
            associated = next((d for d in self.files if d.recovery_id == entry.id), None)
            if associated is not None:
                result.append(associated)
                continue
            current = self.session.find_path(entry.path) if entry.path is not None else None
            disk = read_text(entry.path) if entry.path is not None and entry.path.exists() else None
            conflict = entry.path is not None and disk != (entry.baseline if entry.autosave_eligible else None)
            # Never silently replace an already-edited or independently recovered tab.
            if current is not None and (current.modified or current.recovery_id is not None):
                current = None
                conflict = entry.path is not None
            if current is None:
                current = self.session.add(SessionFile(
                    path=entry.path,
                    draft_name=self.session.draft_name() if entry.path is None else "draft",
                ))
            current.text = entry.text
            current.baseline = entry.baseline
            current.newline = entry.newline
            current.autosave_eligible = entry.autosave_eligible
            current.recovery_id = entry.id
            current.conflict = conflict
            current.disk_text = disk
            self.session.active = current
            result.append(current)
        return tuple(result)

    def resolve_recovery(self, document: Document, choice: Literal["recovered", "disk", "draft"]) -> None:
        """Resolve a cached-version conflict without writing destination files.

        Args:
            document: Conflicting open document handle or destination.
            choice: ``recovered`` restores cached text for its original destination;
                ``disk`` discards the snapshot and adopts destination text (or an
                empty named draft when missing); ``draft`` keeps cached text in a
                separate unnamed draft with its recovery association retained.

        Raises:
            ValueError: If the choice is invalid, no conflict exists, or another
                unsaved document blocks the choice. Rejected choices preserve
                the snapshot and document state.
            OSError: If preparing the destination-version document fails.
        """
        current = self.session.resolve(document)
        if not current.conflict:
            raise ValueError("Document has no unresolved recovery conflict")
        if choice not in ("recovered", "disk", "draft"):
            raise ValueError("Choose recovered, disk, or draft")
        # Validate and prepare before removing snapshots or changing documents.
        other = next((d for d in self.files if d is not current and current.path is not None
                      and d.path is not None and (d.path == current.path or
                      (d.path.exists() and current.path.exists() and d.path.samefile(current.path)))), None)
        if choice != "draft" and other is not None and (other.modified or other.recovery_id is not None):
            raise ValueError("Path has another unsaved document; keep recovery as a draft")
        original = current.path
        prepared = None
        if choice == "draft" and original is not None and original.exists() and other is None:
            text = read_text(original)
            prepared = SessionFile(original, text, text, True, line_ending(text))
        if choice == "disk":
            if current.recovery_id is not None:
                self._recovery.remove(current.recovery_id)
                current.recovery_id = None
            current.text = current.disk_text or ""
            current.newline = line_ending(current.text)
        if choice == "draft":
            # Keep the disk version in its named tab, and retain snapshot ownership
            # on the recovered draft until it is explicitly saved or discarded.
            current.path = None
            current.draft_name = self.session.draft_name()
            current.baseline = ""
            current.autosave_eligible = False
            if prepared is not None:
                self.session.add(prepared)
        else:
            if other is not None and other is not current:
                self.session.remove(other)
            current.baseline = current.disk_text or ""
            current.autosave_eligible = current.disk_text is not None
        current.conflict = False
        current.disk_text = None
        self.session.active = current

    def clear_cache(self) -> None:
        """Purge snapshots without prompting or changing open documents/files.

        Confirmation and the force flag belong to CLI purge, not this headless API.
        """
        self._recovery.purge()

    def list(self, cache: bool = False) -> tuple[SessionFile | CacheFile, ...]:
        """List session documents, optionally followed by all recovery entries.

        Args:
            cache: Include persisted snapshots, even when associated with an
                already-open document. Reading does not restore or consume them.

        Returns:
            Open handles in session order, followed by snapshots when requested.
        """
        return self.files + self.cache if cache else self.files

    def autosave(self) -> tuple[tuple[SessionFile, Exception], ...]:
        """Perform one autosave tick without scheduling a timer.

        Only modified, previously loaded or saved documents without recovery
        conflicts are eligible. A configured interval of zero disables this call.

        Returns:
            ``(document, exception)`` pairs for caught filesystem or validation
            failures. Other eligible documents are still attempted; an empty
            tuple means no caught failures, including when no writes are needed.
        """
        if self.conf.get("auto_save") == 0:
            return ()
        errors = []
        for document in self.files:
            if document.modified and document.autosave_eligible and not document.conflict:
                try:
                    self.save(document)
                except (OSError, ValueError) as error:
                    errors.append((document, error))
        return tuple(errors)

    def run(self, *, create_draft: bool = False) -> None:
        """Restore when configured, then launch the blocking file-editor TUI.

        ``auto_restore`` is evaluated at launch, never during construction/open.
        Existing restoration is idempotent, including earlier explicit calls.
        ``create_draft`` adds a fallback only if no documents remain after restore;
        the CLI requests this, while API callers default to an empty workspace.
        Interactive terminal input and output are required.

        Args:
            create_draft: Create an unnamed draft if the workspace is empty
                after any configured restoration.

        Raises:
            RuntimeError: If stdin or stdout is not an interactive terminal.
            ValueError: If automatic recovery encounters invalid content.
            OSError: If automatic recovery cannot read persisted content.
        """
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("The file editor requires interactive terminal input and output")
        if self.conf.get("auto_restore"):
            self.restore()
        if create_draft and not self.files:
            self.new()
        from .file_app import FileEditorApp

        self.exited = False
        FileEditorApp(self).run()
