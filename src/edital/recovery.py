"""Versioned, entry-scoped snapshots of unsaved UTF-8 documents."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from .documents import SessionFile
from .persistence import write_text
from .session import line_ending


@dataclass(frozen=True)
class CacheFile:
    """Recovery metadata and exact content; not an always-dirty session document."""

    id: str
    path: Path | None
    text: str
    baseline: str
    newline: str
    autosave_eligible: bool
    timestamp: str
    version: int = 1

    @property
    def size(self) -> int:
        """Content size in UTF-8 bytes, excluding snapshot metadata."""
        return len(self.text.encode("utf-8"))


class RecoveryStore:
    """Persist and manage independent entries without consuming them on read."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _entry(self, identity: str) -> Path:
        # IDs originate from UUIDs; validation also prevents path traversal on read.
        return self.path / f"{UUID(identity).hex}.json"

    def snapshot(self, document: SessionFile) -> None:
        """Persist a document before removal; failures retain its prior association."""
        identity = document.recovery_id or document.id
        entry = CacheFile(identity, document.path, document.text, document.baseline,
                          document.newline, document.autosave_eligible,
                          datetime.now(UTC).isoformat())
        payload = asdict(entry)
        payload["path"] = str(entry.path) if entry.path is not None else None
        self.path.mkdir(parents=True, exist_ok=True)
        write_text(self._entry(identity), json.dumps(payload, ensure_ascii=False))
        document.recovery_id = identity

    def entries(self) -> tuple[CacheFile, ...]:
        """Read validated snapshots; corrupt entries raise an actionable ValueError."""
        result = []
        for path in sorted(self.path.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload["version"] != 1:
                    raise ValueError("Unsupported snapshot version")
                for key in ("id", "text", "baseline", "newline", "timestamp"):
                    if not isinstance(payload[key], str):
                        raise TypeError(f"Invalid {key}")
                if type(payload["autosave_eligible"]) is not bool:
                    raise ValueError("Invalid eligibility")
                if payload["path"] is not None and not isinstance(payload["path"], str):
                    raise ValueError("Invalid path")
                if self._entry(payload["id"]).name != path.name:
                    raise ValueError("Snapshot ID does not match its filename")
                line_ending(payload["text"])
                line_ending(payload["baseline"])
                if payload["newline"] not in ("\n", "\r\n"):
                    raise ValueError("Invalid newline convention")
                payload["path"] = Path(payload["path"]) if payload["path"] is not None else None
                result.append(CacheFile(**payload))
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"Invalid recovery entry {path}: {error}") from error
        return tuple(result)

    def remove(self, identity: str) -> None:
        """Remove only the associated persisted entry, if still present."""
        self._entry(identity).unlink(missing_ok=True)

    def purge(self) -> None:
        """Remove persisted entries even when they cannot be decoded."""
        for path in self.path.glob("*.json"):
            path.unlink()
