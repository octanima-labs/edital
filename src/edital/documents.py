"""Framework-independent file documents, identity, and persistence."""

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from .persistence import read_text, write_text
from .session import line_ending


@dataclass(eq=False)
class SessionFile:
    """An addressable document whose dirty state compares text to its saved baseline.

    ``path`` is an optional destination; ``autosave_eligible`` records successful
    loading or saving, not merely path existence. Text uses exact LF/CRLF strings.
    """

    path: Path | None = None
    text: str = ""
    baseline: str = ""
    autosave_eligible: bool = False
    newline: str = "\n"
    id: str = field(default_factory=lambda: uuid4().hex)
    draft_name: str = "draft"
    recovery_id: str | None = None
    conflict: bool = False
    disk_text: str | None = None

    @property
    def modified(self) -> bool:
        """Whether current text differs from the last successful saved revision."""
        return self.text != self.baseline

    @property
    def needs_save_as(self) -> bool:
        """Whether an interactive save must first collect a destination."""
        return self.path is None

    @property
    def unsaved(self) -> bool:
        """Whether content needs saving, including pristine never-saved drafts."""
        return self.modified or not self.autosave_eligible or self.conflict


Document = SessionFile | str | Path


class EditalSession:
    """Ordered documents with active selection and headless save operations."""

    def __init__(self) -> None:
        self._files: list[SessionFile] = []
        self.active: SessionFile | None = None
        self._draft_number = 0

    @property
    def files(self) -> tuple[SessionFile, ...]:
        """Read-only ordered view of open documents."""
        return tuple(self._files)

    def draft_name(self) -> str:
        """Allocate a stable draft label without reusing closed labels."""
        number = self._draft_number
        self._draft_number += 1
        return "draft" if number == 0 else f"draft ({number})"

    def find_path(self, path: str | Path) -> SessionFile | None:
        """Find an already-open destination using normalized filesystem identity."""
        resolved = Path(path).expanduser().resolve()
        for document in self._files:
            if document.path is not None:
                if document.path == resolved:
                    return document
                if document.path.exists() and resolved.exists() and document.path.samefile(resolved):
                    return document
        return None

    def resolve(self, document: Document) -> SessionFile:
        """Resolve a current handle or destination; stale handles raise ValueError."""
        if isinstance(document, SessionFile):
            if document in self._files:
                return document
        else:
            found = self.find_path(document)
            if found is not None:
                return found
        raise ValueError("Document is not open in this session")

    def add(self, document: SessionFile) -> SessionFile:
        """Attach a prepared document and select it."""
        self._files.append(document)
        self.active = document
        return document

    def new(self) -> SessionFile:
        """Prepare a fresh unnamed draft without writing anything."""
        return self.add(SessionFile(draft_name=self.draft_name()))

    def open(self, *paths: str | Path) -> tuple[SessionFile, ...]:
        """Load existing UTF-8 documents or prepare named drafts for missing paths."""
        result = []
        for value in paths:
            path = Path(value).expanduser().resolve()
            document = self.find_path(path)
            if document is None:
                exists = path.exists()
                text = read_text(path) if exists else ""
                document = self.add(SessionFile(path, text, text, exists, line_ending(text)))
            self.active = document
            result.append(document)
        return tuple(result)

    def save(self, document: Document, *, path: str | Path | None = None) -> None:
        """Save to an explicit or existing destination; never open a UI prompt."""
        current = self.resolve(document)
        if current.conflict:
            raise ValueError("Resolve the recovery conflict before saving")
        destination = Path(path).expanduser().resolve() if path is not None else current.path
        if destination is None:
            raise ValueError("An unnamed draft requires a destination path")
        other = self.find_path(destination)
        if other is not None and other is not current:
            raise ValueError("Destination is already open in another document")
        candidate = current.text
        line_ending(candidate)
        write_text(destination, candidate)
        current.path = destination
        current.baseline = candidate
        current.autosave_eligible = True

    def save_all(self) -> None:
        """Save sequentially; an error does not undo previously completed saves."""
        for document in self.files:
            self.save(document)

    def remove(self, document: Document) -> None:
        """Detach a document after its caller has handled preservation/confirmation."""
        current = self.resolve(document)
        index = self._files.index(current)
        self._files.remove(current)
        if self.active is current:
            self.active = self._files[min(index, len(self._files) - 1)] if self._files else None
