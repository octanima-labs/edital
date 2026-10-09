"""Support ``python -m edital`` alongside the installed console entry point."""

from .cli import main

raise SystemExit(main())
