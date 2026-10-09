"""Validated instance settings and native per-user storage locations."""

import re
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from platformdirs import PlatformDirs


def storage_paths() -> tuple[Path, Path]:
    """Return the configuration file and recovery directory without creating them."""
    dirs = PlatformDirs("edital", appauthor=False, roaming=False)
    return dirs.user_config_path / "conf.yml", dirs.user_state_path / "recovery"


class EditalConf:
    """Load defaults, user YAML, and explicit overrides, in that order.

    ``set`` modifies this instance only. ``path`` exposes the user configuration.
    ``auto_restore`` is a boolean evaluated at editing launch, independently of
    exit caching. Packaged ``defaults.yml`` initializes the user ``conf.yml``.
    Invalid settings raise ``ValueError``; filesystem failures raise ``OSError``.
    """

    def __init__(self, **overrides: Any) -> None:
        self.path, _ = storage_paths()
        resource = files("edital").joinpath("defaults.yml").read_text(encoding="utf-8")
        defaults = yaml.safe_load(resource)
        self._values: dict[str, Any] = {}
        self._listeners: list[Callable[[str], None]] = []
        for key, value in defaults.items():
            self.set(key, value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(resource)
        except FileExistsError:
            pass
        try:
            settings = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ValueError(f"Invalid YAML in {self.path}: {error}") from error
        if settings is None:
            settings = {}
        if not isinstance(settings, dict):
            raise ValueError(f"Configuration {self.path} must contain a mapping")  # noqa: TRY004 - invalid YAML value
        for source in (settings, overrides):
            for key, value in source.items():
                self.set(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """Read an effective setting, returning ``default`` for unknown keys."""
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Validate and update an instance setting without rewriting user YAML."""
        if key == "auto_save":
            if type(value) is not int or value < 0:
                raise ValueError("auto_save must be a nonnegative integer in milliseconds")
        elif key in ("cache", "prompt", "auto_restore"):
            if type(value) is not bool:
                raise ValueError(f"{key} must be a boolean")
        elif key in ("focus_color", "draft_color", "conflict_color"):
            nullable = key != "focus_color"
            if not (nullable and value is None) and not (
                isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value)
            ):
                suffix = " or null (None)" if nullable else ""
                raise ValueError(f"{key} must be a quoted #RRGGBB color{suffix}")
        else:
            raise ValueError(f"Unknown configuration key: {key}")
        self._values[key] = value
        for listener in tuple(self._listeners):
            listener(key)

    def subscribe(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """Subscribe to instance changes; return an unsubscribe function."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)
