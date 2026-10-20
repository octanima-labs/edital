"""Edital: standalone file editing and transactional embedded text editing.

Textual is imported only when a session starts. Embedded callers retain ownership
of validation and persistence; ``Edital`` provides explicit file-session behavior.
"""

import sys
from threading import Event

from .configuration import EditalConf
from .documents import EditalSession, SessionFile
from .editor import ConfirmationRequired, Edital
from .recovery import CacheFile
from .session import EditResult, Validator, line_ending

__all__ = ["CacheFile", "ConfirmationRequired", "EditResult", "Edital", "EditalConf", "EditalSession",
           "SessionFile", "TuiEditor", "Validator", "edit_text"]


def edit_text(initial_text: str = "", *, title: str = "Text editor",
              validator: Validator | None = None,
              cancel_event: Event | None = None) -> EditResult:
    """Block until Save & close or cancellation in an interactive terminal.

    A validator returns an error message to keep editing, or ``None`` to accept.
    Unexpected validator exceptions propagate after terminal cleanup. Text uses
    uniform LF or CRLF separators and is returned without reserialization.

    Args:
        initial_text: Exact text to preload, including any trailing newline.
        title: Display label; this is not a destination file path.
        validator: Optional synchronous callback receiving candidate text.
        cancel_event: Optional caller-owned event, safe to set from another
            thread. When observed, discards immediately without confirmation or
            validation. The event is never cleared by Edital.

    Returns:
        An ``EditResult`` with outcome ``accepted`` and the accepted text, or
        outcome ``cancelled`` and no text. Unchanged and empty text can be accepted.

    Raises:
        ValueError: If initial line endings are mixed or use bare carriage returns.
        RuntimeError: If input/output are not interactive terminals or the session
            terminates without an explicit outcome.

    Notes:
        F2 or F3 validates and accepts text; Ctrl+Q cancels, with discard
        confirmation when text has changed. Escape dismisses the active
        interaction and otherwise does nothing. F4 opens Find and F5 opens
        Find/Replace. The caller is responsible for persisting accepted text;
        this function does not write files or initialize standalone configuration.
        There is no implicit external-editor fallback.

        An already set cancellation event returns cancellation after initial
        text validation, without importing the UI or requiring a terminal.
        Cancellation is cooperative: a running synchronous validator must return
        before it can be observed; unexpected validator exceptions still propagate.
        Once acceptance is finalized, later cancellation cannot replace it.
    """
    line_ending(initial_text)
    if cancel_event is not None and cancel_event.is_set():
        return EditResult("cancelled")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("The embedded editor requires interactive terminal input and output")
    from .app import EditorApp

    app = EditorApp(initial_text, title=title, validator=validator, cancel_event=cancel_event)
    result = app.run()
    if app.failure is not None:
        raise app.failure
    if result is None:
        raise RuntimeError("The editor ended without acceptance or cancellation")
    return result


class TuiEditor:
    """Text-session adapter for applications embedding the default editor."""

    def edit(self, initial_text: str = "", *, title: str = "Text editor",
             validator: Validator | None = None,
             cancel_event: Event | None = None) -> EditResult:
        """Run a blocking session with the same contract as :func:`edit_text`."""
        return edit_text(initial_text, title=title, validator=validator, cancel_event=cancel_event)
