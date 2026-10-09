"""Edital's framework-independent editing outcomes and text fidelity helpers."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

Validator = Callable[[str], str | None]


@dataclass(frozen=True)
class EditResult:
    """An explicit outcome; accepted empty text is distinct from cancellation.

    Args:
        outcome: ``accepted`` or ``cancelled``.
        text: Required for acceptance, including an empty string. Must be
            ``None`` for cancellation.

    Raises:
        ValueError: If outcome and text are inconsistent.
    """

    outcome: Literal["accepted", "cancelled"]
    text: str | None = None

    def __post_init__(self) -> None:
        if self.outcome == "accepted" and self.text is None:
            raise ValueError("An accepted result requires text")
        if self.outcome == "cancelled" and self.text is not None:
            raise ValueError("A cancelled result cannot contain accepted text")


def line_ending(text: str) -> str:
    """Identify uniform LF/CRLF text, rejecting mixed or bare-CR separators."""
    remainder = text.replace("\r\n", "")
    if "\r" in remainder or ("\r\n" in text and "\n" in remainder):
        raise ValueError("Mixed or bare-CR line endings are unsupported; convert the document to LF or CRLF first")
    return "\r\n" if "\r\n" in text else "\n"
